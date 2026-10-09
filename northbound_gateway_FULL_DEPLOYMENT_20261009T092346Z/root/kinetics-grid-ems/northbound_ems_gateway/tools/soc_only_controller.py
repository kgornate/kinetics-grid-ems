#!/usr/bin/env python3
"""SOC field controller for two Chinese EMS/BESS units with optional Solis RTU solar control.

Confirmed BESS commands:
- BESS ON  = Manual Mode + Standby  (manual_auto_mode=0, manual_mode_control=2)
- BESS OFF = Manual Mode + Shutdown (manual_auto_mode=0, manual_mode_control=1)

v1.10 field change:
- Lower SOC cutoff is now optional/config gated.
- Low cutoff states are no longer permanent blockers. If the latest SOC has recovered
  above low_recovery_limit, stale X/Y/BOTH low-cutoff state is cleared and the
  controller resumes normal/upper-limit logic.
- This matches the field workflow where an operator may manually inspect/turn on
  a BESS, after which the gateway continuously reads latest SOC and updates state.
- Upper SOC and Solis transition-aware behavior from v1.8 is preserved.

Default mode is dry-run. Use --live --force only after validating decisions.

v1.12 adds an operator-facing status snapshot and transition/event history that the
main northbound FastAPI gateway exposes to Flutter.

v1.14 adds the PV Powertech SOC-based solar derating strategy validated in field:
- both BESS SOC > derate_soc_limit (default 90%) -> keep Solis ON and limit active power
  to derate_power_kw (default 20 kW)
- both BESS SOC >= high_limit (default 98%) -> retain the existing Solis OFF logic
- one BESS above the derate threshold while the other is <= it -> normal solar output
- field-proven Solis active-power control uses FC06/FC03 holding register 3051
  (10000 = 100%); 20 kW on the validated 100 kW inverter maps to raw 2000 (20%).
"""
from __future__ import annotations

import argparse
import json
import signal
import struct
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    from pymodbus.client import ModbusTcpClient
except Exception as exc:  # pragma: no cover
    print(f"ERROR: pymodbus TCP import failed: {exc}", file=sys.stderr)
    raise

try:
    from pymodbus.client import ModbusSerialClient
except Exception:  # pragma: no cover
    ModbusSerialClient = None  # type: ignore[assignment]

try:
    import serial
except Exception:  # pragma: no cover
    serial = None  # type: ignore[assignment]

# The field controller runs as a standalone tool from the repository checkout.
# Add the source tree explicitly so it can share the operator-monitor store with
# the main FastAPI gateway without requiring a separate installation step.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

try:
    from nb_ems_gateway.operator_control.store import ControllerMonitorStore
except Exception as exc:  # pragma: no cover
    ControllerMonitorStore = None  # type: ignore[assignment,misc]
    _MONITOR_IMPORT_ERROR = str(exc)
else:
    _MONITOR_IMPORT_ERROR = None

try:
    from nb_ems_gateway.operator_control.settings import ControllerSettingsStore
except Exception as exc:  # pragma: no cover
    ControllerSettingsStore = None  # type: ignore[assignment,misc]
    _SETTINGS_IMPORT_ERROR = str(exc)
else:
    _SETTINGS_IMPORT_ERROR = None


@dataclass(frozen=True)
class EMSDevice:
    name: str
    host: str
    port: int = 502
    unit_id: int = 1


@dataclass
class EMSRuntime:
    device: EMSDevice
    client: ModbusTcpClient
    soc: float | None = None
    last_commanded_state: str | None = None
    online: bool = False
    last_error: str | None = None


@dataclass(frozen=True)
class SolisConfig:
    enabled: bool = False
    transport: str = "rtu"
    serial_port: str = "/dev/ttyUSB1"
    baudrate: int = 9600
    unit_id: int = 1
    timeout: float = 3.0
    control_method: str = "holding_onoff_3006"
    status_read_enabled: bool = True
    rated_power_kw: float = 100.0
    normal_power_percent: float = 110.0


# Chinese EMS / Unity261PV confirmed registers, Float32 encoded.
REG_MANUAL_AUTO_MODE = 10          # 0=Manual, 1=Auto
REG_MANUAL_MODE_CONTROL = 12       # 1=Shutdown/OFF, 2=Standby/ON, 3=Charge, 4=Discharge
REG_SOC = 80                       # SOC %, Float32

# Optional future BESS registers. Disabled by default in field config.
REG_ON_OFF_GRID_SWITCHING = 164    # 1=Grid-tied, 2=Off-grid
REG_SYSTEM_FAULT_RESET = 2704      # 0=Normal, 1=Reset. Some units reject this.

# Solis RTU commands from Solis protocol.
SOLIS_COIL_GRID_ON_OFF_5000 = 5000
SOLIS_HOLDING_ON_OFF_REGISTER = 3006
SOLIS_HOLDING_ON_VALUE = 0x00BE
SOLIS_HOLDING_OFF_VALUE = 0x00DE
SOLIS_POWER_CONTROL_ENABLE_REGISTER = 3069
SOLIS_POWER_CONTROL_ENABLE_VALUE = 0x00AA
SOLIS_POWER_LIMIT_PERCENT_REGISTER = 3051
SOLIS_POWER_LIMIT_PERCENT_FEEDBACK_REGISTER = 3049
SOLIS_LIMITED_POWER_FEEDBACK_REGISTER = 3044
SOLIS_POWER_LIMIT_SWITCH_FEEDBACK_REGISTER = 3089
SOLIS_LIMITING_STATUS_REGISTER = 3094

STATE_NORMAL = "NORMAL"
STATE_X_HIGH_ONLY = "X_HIGH_ONLY"
STATE_Y_HIGH_ONLY = "Y_HIGH_ONLY"
STATE_BOTH_SOLAR_DERATED = "BOTH_SOLAR_DERATED"
STATE_BOTH_HIGH_SOLAR_OFF = "BOTH_HIGH_SOLAR_OFF"
STATE_X_LOW_CUTOFF = "X_LOW_CUTOFF"
STATE_Y_LOW_CUTOFF = "Y_LOW_CUTOFF"
STATE_BOTH_LOW_CUTOFF_LOCKOUT = "BOTH_LOW_CUTOFF_LOCKOUT"

SOLAR_NORMAL = "ON_NORMAL"
SOLAR_DERATED = "ON_DERATED"
SOLAR_OFF = "OFF"
SOLAR_HOLD = "HOLD"

_stop = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _handle_stop(signum, frame):  # pragma: no cover
    global _stop
    _stop = True


def encode_float32(value: float, byte_order: str = "ABCD") -> list[int]:
    raw = struct.pack(">f", float(value))
    b = list(raw)
    if byte_order == "ABCD":
        ordered = b
    elif byte_order == "BADC":
        ordered = [b[1], b[0], b[3], b[2]]
    elif byte_order == "CDAB":
        ordered = [b[2], b[3], b[0], b[1]]
    elif byte_order == "DCBA":
        ordered = [b[3], b[2], b[1], b[0]]
    else:
        raise ValueError(f"Unsupported byte_order={byte_order}")
    return [(ordered[0] << 8) | ordered[1], (ordered[2] << 8) | ordered[3]]


def decode_float32(registers: Iterable[int], byte_order: str = "ABCD") -> float:
    regs = list(registers)
    if len(regs) != 2:
        raise ValueError(f"Float32 decode needs exactly 2 registers, got {len(regs)}")
    b = [(regs[0] >> 8) & 0xFF, regs[0] & 0xFF, (regs[1] >> 8) & 0xFF, regs[1] & 0xFF]
    if byte_order == "ABCD":
        ordered = b
    elif byte_order == "BADC":
        ordered = [b[1], b[0], b[3], b[2]]
    elif byte_order == "CDAB":
        ordered = [b[2], b[3], b[0], b[1]]
    elif byte_order == "DCBA":
        ordered = [b[3], b[2], b[1], b[0]]
    else:
        raise ValueError(f"Unsupported byte_order={byte_order}")
    return float(struct.unpack(">f", bytes(ordered))[0])


def try_modbus_call(callables: list[Callable[[], Any]]) -> Any:
    last_type_error: TypeError | None = None
    for call in callables:
        try:
            return call()
        except TypeError as exc:
            last_type_error = exc
            continue
    if last_type_error:
        raise last_type_error
    raise RuntimeError("No compatible pymodbus call signature matched")


def _is_modbus_error(resp: Any) -> bool:
    return resp is None or getattr(resp, "isError", lambda: False)()


class SolisRawRTUClient:
    """Small raw Modbus-RTU transport for the field-proven Solis control path.

    The inverter link can contain unrelated/leading bytes, so transactions collect a
    bounded RX window and scan for a CRC-valid frame instead of assuming byte zero is
    the response start. FC06 success is verified by FC03 readback of holding 3006.
    """

    def __init__(self, *, port: str, baudrate: int, unit_id: int, timeout: float):
        if serial is None:
            raise RuntimeError("pyserial is not available")
        self.port = port
        self.baudrate = int(baudrate)
        self.unit_id = int(unit_id)
        self.timeout = float(timeout)
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=0.05,
        )

    @staticmethod
    def crc16(data: bytes) -> int:
        crc = 0xFFFF
        for b in data:
            crc ^= b
            for _ in range(8):
                crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        return crc

    @classmethod
    def crc_ok(cls, frame: bytes) -> bool:
        if len(frame) < 4:
            return False
        got = frame[-2] | (frame[-1] << 8)
        return got == cls.crc16(frame[:-2])

    def _build(self, function: int, address: int, value_or_count: int) -> bytes:
        body = bytes([
            self.unit_id,
            function,
            (address >> 8) & 0xFF,
            address & 0xFF,
            (value_or_count >> 8) & 0xFF,
            value_or_count & 0xFF,
        ])
        crc = self.crc16(body)
        return body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    def _collect(self, seconds: float | None = None) -> bytes:
        rx = bytearray()
        deadline = time.monotonic() + max(0.4, float(seconds or self.timeout))
        while time.monotonic() < deadline:
            chunk = self.ser.read(256)
            if chunk:
                rx.extend(chunk)
            else:
                time.sleep(0.01)
        return bytes(rx)

    def _read_until_frame(self, *, function: int, expected_len: int, byte_count: int | None = None, timeout: float | None = None) -> tuple[bytes | None, bytes, int | None]:
        rx = bytearray()
        deadline = time.monotonic() + max(0.4, float(timeout or self.timeout))
        while time.monotonic() < deadline:
            chunk = self.ser.read(256)
            if chunk:
                rx.extend(chunk)
                for i in range(max(0, len(rx) - expected_len + 1)):
                    frame = bytes(rx[i:i + expected_len])
                    if len(frame) != expected_len:
                        continue
                    if frame[0] != self.unit_id or frame[1] != function:
                        continue
                    if byte_count is not None and frame[2] != byte_count:
                        continue
                    if self.crc_ok(frame):
                        return frame, bytes(rx), i
            else:
                time.sleep(0.01)
        return None, bytes(rx), None

    def _prepare(self, guard_sec: float = 0.40) -> None:
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        if guard_sec > 0:
            time.sleep(guard_sec)

    def read_holding_u16(self, address: int) -> dict[str, Any]:
        req = self._build(0x03, address, 1)
        self._prepare(0.35)
        self.ser.write(req)
        self.ser.flush()
        frame, rx, pos = self._read_until_frame(function=0x03, expected_len=7, byte_count=2)
        if frame is not None and pos is not None:
            value = (frame[3] << 8) | frame[4]
            return {
                "ok": True,
                "value": value,
                "request_hex": req.hex(" "),
                "frame_hex": frame.hex(" "),
                "extra_before_hex": rx[:pos].hex(" "),
                "extra_after_hex": rx[pos + 7:pos + 47].hex(" "),
                "raw_rx_len": len(rx),
            }
        return {"ok": False, "request_hex": req.hex(" "), "raw_rx_hex": rx[:120].hex(" "), "raw_rx_len": len(rx)}

    def read_input_u16s(self, address: int, count: int) -> dict[str, Any]:
        req = self._build(0x04, address, count)
        expected = 5 + 2 * count
        self._prepare(0.35)
        self.ser.write(req)
        self.ser.flush()
        frame, rx, _ = self._read_until_frame(function=0x04, expected_len=expected, byte_count=2 * count)
        if frame is not None:
            values = []
            for n in range(count):
                p = 3 + 2 * n
                values.append((frame[p] << 8) | frame[p + 1])
            return {
                "ok": True,
                "values": values,
                "request_hex": req.hex(" "),
                "frame_hex": frame.hex(" "),
                "raw_rx_len": len(rx),
            }
        return {"ok": False, "request_hex": req.hex(" "), "raw_rx_hex": rx[:120].hex(" "), "raw_rx_len": len(rx)}

    def write_holding_u16_verified(self, address: int, value: int, *, retries: int = 2) -> dict[str, Any]:
        req = self._build(0x06, address, value)
        attempts: list[dict[str, Any]] = []
        for attempt in range(1, max(1, retries) + 1):
            self._prepare(0.80)
            self.ser.write(req)
            self.ser.flush()

            rx = bytearray()
            ack_found = False
            deadline = time.monotonic() + min(max(self.timeout, 0.8), 1.5)
            while time.monotonic() < deadline:
                chunk = self.ser.read(256)
                if chunk:
                    rx.extend(chunk)
                    if any(rx[i:i + 8] == req for i in range(max(0, len(rx) - 7))):
                        ack_found = True
                        break
                else:
                    time.sleep(0.01)

            # The field-proven success criterion is FC03 readback. This also handles
            # cases where the inverter executes FC06 but the echo is obscured by
            # unrelated bytes on the shared serial stream.
            time.sleep(0.80)
            readback = self.read_holding_u16(address)
            verified = bool(readback.get("ok") and int(readback.get("value")) == int(value))
            attempts.append({
                "attempt": attempt,
                "ack_found": ack_found,
                "write_request_hex": req.hex(" "),
                "write_rx_len": len(rx),
                "write_rx_preview_hex": bytes(rx[:100]).hex(" "),
                "readback": readback,
                "verified": verified,
            })
            if verified:
                return {"ok": True, "ack_found": ack_found, "readback_verified": True, "value": value, "attempts": attempts}
        return {"ok": False, "ack_found": False, "readback_verified": False, "value": value, "attempts": attempts}

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass


def read_holding_registers(client: Any, address: int, count: int, unit_id: int) -> Any:
    return try_modbus_call([
        lambda: client.read_holding_registers(address=address, count=count, device_id=unit_id),
        lambda: client.read_holding_registers(address, count=count, device_id=unit_id),
        lambda: client.read_holding_registers(address=address, count=count, slave=unit_id),
        lambda: client.read_holding_registers(address, count=count, slave=unit_id),
        lambda: client.read_holding_registers(address=address, count=count, unit=unit_id),
        lambda: client.read_holding_registers(address, count=count, unit=unit_id),
        lambda: client.read_holding_registers(address, count, slave=unit_id),
        lambda: client.read_holding_registers(address, count, unit=unit_id),
        lambda: client.read_holding_registers(address, count),
        lambda: client.read_holding_registers(address=address, count=count),
    ])


def read_input_registers(client: Any, address: int, count: int, unit_id: int) -> Any:
    return try_modbus_call([
        lambda: client.read_input_registers(address=address, count=count, device_id=unit_id),
        lambda: client.read_input_registers(address, count=count, device_id=unit_id),
        lambda: client.read_input_registers(address=address, count=count, slave=unit_id),
        lambda: client.read_input_registers(address, count=count, slave=unit_id),
        lambda: client.read_input_registers(address=address, count=count, unit=unit_id),
        lambda: client.read_input_registers(address, count=count, unit=unit_id),
        lambda: client.read_input_registers(address, count, slave=unit_id),
        lambda: client.read_input_registers(address, count, unit=unit_id),
        lambda: client.read_input_registers(address, count),
        lambda: client.read_input_registers(address=address, count=count),
    ])


def write_registers(client: Any, address: int, values: list[int], unit_id: int) -> Any:
    return try_modbus_call([
        lambda: client.write_registers(address=address, values=values, device_id=unit_id),
        lambda: client.write_registers(address, values, device_id=unit_id),
        lambda: client.write_registers(address=address, values=values, slave=unit_id),
        lambda: client.write_registers(address, values, slave=unit_id),
        lambda: client.write_registers(address=address, values=values, unit=unit_id),
        lambda: client.write_registers(address, values, unit=unit_id),
        lambda: client.write_registers(address, values),
    ])


def write_register(client: Any, address: int, value: int, unit_id: int) -> Any:
    return try_modbus_call([
        lambda: client.write_register(address=address, value=value, device_id=unit_id),
        lambda: client.write_register(address, value, device_id=unit_id),
        lambda: client.write_register(address=address, value=value, slave=unit_id),
        lambda: client.write_register(address, value, slave=unit_id),
        lambda: client.write_register(address=address, value=value, unit=unit_id),
        lambda: client.write_register(address, value, unit=unit_id),
        lambda: client.write_register(address, value),
    ])


def write_coil(client: Any, address: int, value: bool, unit_id: int) -> Any:
    return try_modbus_call([
        lambda: client.write_coil(address=address, value=value, device_id=unit_id),
        lambda: client.write_coil(address, value, device_id=unit_id),
        lambda: client.write_coil(address=address, value=value, slave=unit_id),
        lambda: client.write_coil(address, value, slave=unit_id),
        lambda: client.write_coil(address=address, value=value, unit=unit_id),
        lambda: client.write_coil(address, value, unit=unit_id),
        lambda: client.write_coil(address, value),
    ])


def _read_ems_float_once(client: ModbusTcpClient, address: int, unit_id: int, byte_order: str) -> float:
    rr = read_holding_registers(client, address, 2, unit_id)
    if _is_modbus_error(rr):
        raise RuntimeError(f"Modbus read failed addr={address} response={rr}")
    return decode_float32(list(rr.registers), byte_order)


def _write_ems_float_once(client: ModbusTcpClient, address: int, value: float, unit_id: int, byte_order: str, readback: bool = True) -> dict[str, Any]:
    regs = encode_float32(value, byte_order)
    rr = write_registers(client, address, regs, unit_id)

    if _is_modbus_error(rr):
        raise RuntimeError(
            f"Modbus write failed addr={address} value={value} response={rr}"
        )

    out: dict[str, Any] = {
        "address": address,
        "value": float(value),
        "raw_registers": regs,
    }

    if readback:
        attempts = []

        for attempt in range(1, 4):
            time.sleep(0.5)

            actual = read_ems_float(
                client,
                address,
                unit_id,
                byte_order,
            )

            attempts.append({
                "attempt": attempt,
                "value": actual,
            })

            if abs(actual - float(value)) < 0.001:
                out["readback"] = actual
                out["readback_verified"] = True
                out["readback_attempts"] = attempts
                return out

        out["readback"] = attempts[-1]["value"]
        out["readback_verified"] = False
        out["readback_attempts"] = attempts

        raise RuntimeError(
            f"BESS write verification failed addr={address} "
            f"requested={value} readback={attempts[-1]['value']}"
        )

    return out



# ---------------------------------------------------------------------------
# AUTO_RECONNECT_V1
#
# Field self-recovery for stale/broken EMS Modbus-TCP sessions.
#
# The original read/write implementations are preserved as:
#
#   _read_ems_float_once()
#   _write_ems_float_once()
#
# These wrappers close and reconnect the SAME ModbusTcpClient whenever an
# operation throws a communication exception, then retry the operation.
#
# This does NOT change SOC logic, thresholds, register addresses, byte order,
# BESS commands or Solis control behavior.
# ---------------------------------------------------------------------------

def _ems_operation_with_reconnect(
    client: ModbusTcpClient,
    operation: Any,
    operation_name: str,
    max_attempts: int = 3,
) -> Any:
    import time as _time

    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return operation()

        except Exception as exc:
            last_exc = exc

            print(
                f"[EMS-RECONNECT] {operation_name} failed "
                f"attempt={attempt}/{max_attempts}: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )

            if attempt >= max_attempts:
                break

            # Throw away the stale TCP socket.
            try:
                client.close()
            except Exception:
                pass

            # Small backoff so the remote EMS TCP server has time to recover.
            delay = 0.5 * attempt
            _time.sleep(delay)

            try:
                connected = client.connect()

                # pymodbus normally returns bool. Treat explicit False as
                # failure; tolerate versions which return None on success.
                if connected is False:
                    raise ConnectionError(
                        "ModbusTcpClient.connect() returned False"
                    )

                print(
                    f"[EMS-RECONNECT] {operation_name}: "
                    f"TCP reconnect successful",
                    flush=True,
                )

            except Exception as reconnect_exc:
                last_exc = reconnect_exc

                print(
                    f"[EMS-RECONNECT] {operation_name}: "
                    f"reconnect failed: "
                    f"{type(reconnect_exc).__name__}: "
                    f"{reconnect_exc}",
                    flush=True,
                )

    if last_exc is not None:
        raise last_exc

    raise RuntimeError(
        f"{operation_name}: Modbus operation failed without exception"
    )


def read_ems_float(
    client: ModbusTcpClient,
    address: int,
    unit_id: int,
    byte_order: str,
) -> float:

    return _ems_operation_with_reconnect(
        client,
        lambda: _read_ems_float_once(
            client,
            address,
            unit_id,
            byte_order,
        ),
        operation_name=f"EMS read address={address}",
    )


def write_ems_float(
    client: ModbusTcpClient,
    address: int,
    value: float,
    unit_id: int,
    byte_order: str,
    readback: bool = True,
) -> dict[str, Any]:

    return _ems_operation_with_reconnect(
        client,
        lambda: _write_ems_float_once(
            client,
            address,
            value,
            unit_id,
            byte_order,
            readback,
        ),
        operation_name=f"EMS write address={address}",
    )


def make_ems_client(device: EMSDevice, timeout: float) -> ModbusTcpClient:
    client = ModbusTcpClient(host=device.host, port=device.port, timeout=timeout)
    if not client.connect():
        raise RuntimeError(f"Could not connect to {device.name} {device.host}:{device.port}")
    return client


def make_solis_client(cfg: SolisConfig) -> Any:
    if not cfg.enabled:
        return None
    if cfg.transport != "rtu":
        raise ValueError("This field build supports Solis RTU only. Set solis.transport=rtu.")
    return SolisRawRTUClient(
        port=cfg.serial_port,
        baudrate=cfg.baudrate,
        unit_id=cfg.unit_id,
        timeout=cfg.timeout,
    )


def load_controller_state(path: str, *, clear: bool = False) -> dict[str, Any]:
    if clear:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:
            pass
        return {"state": STATE_NORMAL, "solar_off_reason": None, "low_cutoff_reason": None, "soc_history": []}
    try:
        data = json.loads(Path(path).read_text())
        if not isinstance(data, dict):
            raise ValueError("state file is not a JSON object")
        data.setdefault("state", STATE_NORMAL)
        data.setdefault("solar_off_reason", None)
        data.setdefault("low_cutoff_reason", None)
        data.setdefault("soc_history", [])
        return data
    except FileNotFoundError:
        return {"state": STATE_NORMAL, "solar_off_reason": None, "low_cutoff_reason": None, "soc_history": []}
    except Exception as exc:
        return {"state": STATE_NORMAL, "solar_off_reason": None, "low_cutoff_reason": None, "soc_history": [], "state_load_error": str(exc)}


def save_controller_state(path: str, state: dict[str, Any]) -> None:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, indent=2))
    except Exception as exc:
        print(json.dumps({"timestamp_utc": utc_now(), "event": "state_save_failed", "path": path, "error": str(exc)}, indent=2), file=sys.stderr)


def update_soc_history(state: dict[str, Any], soc_x: float, soc_y: float, *, window_sec: float) -> dict[str, Any]:
    now = time.time()
    history = list(state.get("soc_history") or [])
    history.append({"t": now, "soc_x": float(soc_x), "soc_y": float(soc_y), "avg_soc": (float(soc_x) + float(soc_y)) / 2.0})
    keep_after = now - max(float(window_sec) * 2.0, float(window_sec) + 10.0, 30.0)
    history = [h for h in history if float(h.get("t", 0)) >= keep_after]
    state["soc_history"] = history

    trend: dict[str, Any] = {"window_sec": float(window_sec), "sample_count": len(history), "avg_soc_delta": None, "oldest_age_sec": None}
    old_candidates = [h for h in history[:-1] if now - float(h.get("t", now)) >= max(1.0, float(window_sec))]
    old = old_candidates[0] if old_candidates else (history[0] if len(history) >= 2 else None)
    if old:
        trend["avg_soc_delta"] = float(history[-1]["avg_soc"]) - float(old["avg_soc"])
        trend["oldest_age_sec"] = round(now - float(old.get("t", now)), 3)
        trend["old_avg_soc"] = float(old["avg_soc"])
        trend["new_avg_soc"] = float(history[-1]["avg_soc"])
    return trend


def decide_states(
    soc_x: float,
    soc_y: float,
    high_limit: float,
    recovery_limit: float,
    low_cutoff_limit: float,
    *,
    derate_soc_limit: float,
    low_cutoff_enabled: bool,
    low_recovery_limit: float,
    controller_state: str,
    avg_soc_delta: float | None,
    trend_negative_delta: float,
) -> tuple[str, dict[str, str], str, str, str | None, str | None, dict[str, Any]]:
    """Return controller decision and desired BESS/Solis state.

    Priority order:
    1. Optional low-SOC BESS protection (existing behavior).
    2. Existing latched BOTH_HIGH solar-OFF recovery behavior.
    3. Both BESS >= high_limit -> solar OFF.
    4. Both BESS > derate_soc_limit -> solar ON but active-power derated.
    5. Otherwise solar ON at normal/unrestricted field setting.

    The derate comparison is intentionally strict (>) to match the approved requirement,
    while the high/OFF comparison remains inclusive (>=).
    """
    low_recovery_limit = max(float(low_recovery_limit), float(low_cutoff_limit))
    derate_soc_limit = float(derate_soc_limit)
    high_limit = float(high_limit)
    low_state_active = controller_state in {STATE_X_LOW_CUTOFF, STATE_Y_LOW_CUTOFF, STATE_BOTH_LOW_CUTOFF_LOCKOUT}

    x_low = bool(low_cutoff_enabled) and soc_x <= low_cutoff_limit
    y_low = bool(low_cutoff_enabled) and soc_y <= low_cutoff_limit
    x_low_recovered = soc_x >= low_recovery_limit
    y_low_recovered = soc_y >= low_recovery_limit
    x_high = soc_x >= high_limit
    y_high = soc_y >= high_limit
    x_above_derate = soc_x > derate_soc_limit
    y_above_derate = soc_y > derate_soc_limit
    both_above_derate = x_above_derate and y_above_derate
    any_at_or_below_recovery = min(soc_x, soc_y) <= recovery_limit
    soc_decreasing = avg_soc_delta is not None and avg_soc_delta < -abs(float(trend_negative_delta))

    info = {
        "state_before": controller_state,
        "low_cutoff_enabled": bool(low_cutoff_enabled),
        "low_state_active": low_state_active,
        "x_low": x_low,
        "y_low": y_low,
        "low_cutoff_limit": low_cutoff_limit,
        "low_recovery_limit": low_recovery_limit,
        "x_low_recovered": x_low_recovered,
        "y_low_recovered": y_low_recovered,
        "derate_soc_limit": derate_soc_limit,
        "x_above_derate": x_above_derate,
        "y_above_derate": y_above_derate,
        "both_above_derate": both_above_derate,
        "high_limit": high_limit,
        "x_high": x_high,
        "y_high": y_high,
        "any_at_or_below_recovery": any_at_or_below_recovery,
        "avg_soc_delta": avg_soc_delta,
        "trend_negative_delta": float(trend_negative_delta),
        "soc_decreasing": soc_decreasing,
    }

    if low_state_active and not low_cutoff_enabled:
        info["low_state_release"] = "low_cutoff_disabled"
        controller_state = STATE_NORMAL

    # Existing lower-side protection remains highest priority when enabled.
    if low_cutoff_enabled:
        if x_low and y_low:
            return "both_low_cutoff_both_off", {"X": "OFF", "Y": "OFF"}, SOLAR_HOLD, STATE_BOTH_LOW_CUTOFF_LOCKOUT, None, "BOTH_SOC_BELOW_LOW_LIMIT", info
        if x_low:
            return "x_low_cutoff_x_off_y_on", {"X": "OFF", "Y": "ON"}, SOLAR_HOLD, STATE_X_LOW_CUTOFF, None, "X_SOC_BELOW_LOW_LIMIT", info
        if y_low:
            return "y_low_cutoff_x_on_y_off", {"X": "ON", "Y": "OFF"}, SOLAR_HOLD, STATE_Y_LOW_CUTOFF, None, "Y_SOC_BELOW_LOW_LIMIT", info

        if controller_state == STATE_BOTH_LOW_CUTOFF_LOCKOUT:
            if x_low_recovered and y_low_recovered:
                info["low_state_release"] = "both_soc_recovered"
                controller_state = STATE_NORMAL
            else:
                return "both_low_cutoff_hold_both_off_until_recovery", {"X": "OFF", "Y": "OFF"}, SOLAR_HOLD, STATE_BOTH_LOW_CUTOFF_LOCKOUT, None, "BOTH_SOC_BELOW_LOW_RECOVERY", info
        elif controller_state == STATE_X_LOW_CUTOFF:
            if x_low_recovered:
                info["low_state_release"] = "x_soc_recovered"
                controller_state = STATE_NORMAL
            else:
                return "x_low_cutoff_hold_x_off_y_on_until_recovery", {"X": "OFF", "Y": "ON"}, SOLAR_HOLD, STATE_X_LOW_CUTOFF, None, "X_SOC_BELOW_LOW_RECOVERY", info
        elif controller_state == STATE_Y_LOW_CUTOFF:
            if y_low_recovered:
                info["low_state_release"] = "y_soc_recovered"
                controller_state = STATE_NORMAL
            else:
                return "y_low_cutoff_hold_x_on_y_off_until_recovery", {"X": "ON", "Y": "OFF"}, SOLAR_HOLD, STATE_Y_LOW_CUTOFF, None, "Y_SOC_BELOW_LOW_RECOVERY", info

    # Retain the previously validated high-SOC OFF latch/recovery semantics exactly.
    if controller_state == STATE_BOTH_HIGH_SOLAR_OFF:
        if any_at_or_below_recovery and soc_decreasing:
            return "post_both_high_recovered_solar_normal_both_bess_on", {"X": "ON", "Y": "ON"}, SOLAR_NORMAL, STATE_NORMAL, None, None, info
        return "both_high_solar_off_waiting_for_recovery", {"X": "ON", "Y": "ON"}, SOLAR_OFF, STATE_BOTH_HIGH_SOLAR_OFF, "BOTH_BESS_HIGH", None, info

    # High/OFF threshold retains existing BESS behavior.
    if x_high and y_high:
        return "both_high_keep_both_on_solar_off", {"X": "ON", "Y": "ON"}, SOLAR_OFF, STATE_BOTH_HIGH_SOLAR_OFF, "BOTH_BESS_HIGH", None, info

    # A single BESS at/above 98% remains protected by switching that BESS OFF.
    # Solar is derated only when BOTH BESS are already above the 90% derate threshold.
    if x_high and not y_high:
        solar_target = SOLAR_DERATED if both_above_derate else SOLAR_NORMAL
        state = STATE_X_HIGH_ONLY
        decision = "only_x_high_x_off_y_on_solar_derated" if both_above_derate else "only_x_high_x_off_y_on_solar_normal"
        return decision, {"X": "OFF", "Y": "ON"}, solar_target, state, None, None, info

    if y_high and not x_high:
        solar_target = SOLAR_DERATED if both_above_derate else SOLAR_NORMAL
        state = STATE_Y_HIGH_ONLY
        decision = "only_y_high_x_on_y_off_solar_derated" if both_above_derate else "only_y_high_x_on_y_off_solar_normal"
        return decision, {"X": "ON", "Y": "OFF"}, solar_target, state, None, None, info

    if both_above_derate:
        return "both_above_90_keep_bess_on_solar_derated", {"X": "ON", "Y": "ON"}, SOLAR_DERATED, STATE_BOTH_SOLAR_DERATED, None, None, info

    return "normal_keep_both_on_solar_normal", {"X": "ON", "Y": "ON"}, SOLAR_NORMAL, STATE_NORMAL, None, None, info


def command_bess(
    rt: EMSRuntime,
    target: str,
    *,
    live: bool,
    byte_order: str,
    readback: bool,
    force: bool,
    enable_reset_before_on: bool,
    enable_offgrid_before_on: bool,
) -> dict[str, Any]:
    if target not in {"ON", "OFF"}:
        raise ValueError(f"Invalid target={target}")
    if not force and rt.last_commanded_state == target:
        return {"device": rt.device.name, "target": target, "skipped": True, "reason": "already_commanded"}

    if not live:
        rt.last_commanded_state = target
        return {"device": rt.device.name, "target": target, "dry_run": True, "writes": []}

    writes = []
    writes.append({"signal": "manual_auto_mode", **write_ems_float(rt.client, REG_MANUAL_AUTO_MODE, 0.0, rt.device.unit_id, byte_order, readback)})

    if target == "ON":
        if enable_reset_before_on:
            writes.append({"signal": "system_fault_reset", **write_ems_float(rt.client, REG_SYSTEM_FAULT_RESET, 1.0, rt.device.unit_id, byte_order, readback)})
            time.sleep(0.2)
            writes.append({"signal": "system_fault_reset", **write_ems_float(rt.client, REG_SYSTEM_FAULT_RESET, 0.0, rt.device.unit_id, byte_order, readback)})
        if enable_offgrid_before_on:
            writes.append({"signal": "on_off_grid_switching", **write_ems_float(rt.client, REG_ON_OFF_GRID_SWITCHING, 2.0, rt.device.unit_id, byte_order, readback)})
            time.sleep(0.2)
        writes.append({"signal": "manual_mode_control", **write_ems_float(rt.client, REG_MANUAL_MODE_CONTROL, 2.0, rt.device.unit_id, byte_order, readback)})
    else:
        writes.append({"signal": "manual_mode_control", **write_ems_float(rt.client, REG_MANUAL_MODE_CONTROL, 1.0, rt.device.unit_id, byte_order, readback)})

    rt.last_commanded_state = target
    return {"device": rt.device.name, "target": target, "dry_run": False, "writes": writes}


def _u16s_to_s32(values: Iterable[int]) -> int:
    regs = list(values)
    if len(regs) != 2:
        raise ValueError(f"S32 decode needs exactly 2 registers, got {len(regs)}")
    raw = (int(regs[0]) << 16) | int(regs[1])
    if raw & 0x80000000:
        raw -= 0x100000000
    return raw


def _percent_to_solis_raw(percent: float) -> int:
    raw = int(round(float(percent) * 100.0))
    if not 0 <= raw <= 11000:
        raise ValueError(f"Solis active-power percentage must map to raw 0..11000, got {raw}")
    return raw


def _kw_to_solis_percent_raw(power_kw: float, rated_power_kw: float) -> int:
    rated = float(rated_power_kw)
    power = float(power_kw)
    if rated <= 0:
        raise ValueError("Solis rated_power_kw must be > 0")
    if power < 0:
        raise ValueError("Solis target power must be >= 0 kW")
    raw = int(round((power / rated) * 10000.0))
    if not 0 <= raw <= 11000:
        raise ValueError(
            f"Solis target {power} kW with rated_power_kw={rated} maps to unsupported raw {raw}"
        )
    return raw


def read_solis_status(client: Any, cfg: SolisConfig, *, extended: bool = False) -> dict[str, Any]:
    if not cfg.enabled:
        return {"enabled": False}
    if not cfg.status_read_enabled:
        return {"enabled": True, "status_read_enabled": False}

    out: dict[str, Any] = {
        "enabled": True,
        "transport": "raw_rtu_pyserial",
        "serial_port": cfg.serial_port,
        "unit_id": cfg.unit_id,
        "rated_power_kw": float(cfg.rated_power_kw),
        "normal_power_percent": float(cfg.normal_power_percent),
    }

    state = client.read_holding_u16(SOLIS_HOLDING_ON_OFF_REGISTER)
    out["on_off_register_3006"] = state
    if state.get("ok"):
        value = int(state["value"])
        out["on_off_state"] = "ON" if value == SOLIS_HOLDING_ON_VALUE else "OFF" if value == SOLIS_HOLDING_OFF_VALUE else f"UNKNOWN_0x{value:04X}"

    # Primary physical feedback: active power FC04 3004-3005, S32, 1 W.
    power = client.read_input_u16s(3004, 2)
    out["active_power"] = power
    if power.get("ok"):
        active_power_w = _u16s_to_s32(power["values"])
        out["active_power_w"] = active_power_w
        out["active_power_kw"] = round(active_power_w / 1000.0, 3)

    # Current active-power percentage command. Field-validated: 11000=110%, 2000=20%.
    pct_setting = client.read_holding_u16(SOLIS_POWER_LIMIT_PERCENT_REGISTER)
    out["power_limit_percent_register_3051"] = pct_setting
    if pct_setting.get("ok"):
        raw = int(pct_setting["value"])
        out["power_limit_percent_raw"] = raw
        out["power_limit_percent"] = raw / 100.0
        out["power_limit_equivalent_kw"] = round(float(cfg.rated_power_kw) * raw / 10000.0, 3)

    # The mirrored percentage feedback is lightweight enough to read each cycle.
    pct_feedback = client.read_input_u16s(SOLIS_POWER_LIMIT_PERCENT_FEEDBACK_REGISTER, 1)
    out["power_limit_percent_feedback_3049"] = pct_feedback
    if pct_feedback.get("ok"):
        raw = int(pct_feedback["values"][0])
        out["power_limit_feedback_raw"] = raw
        out["power_limit_feedback_percent"] = raw / 100.0

    if extended:
        limited = client.read_input_u16s(SOLIS_LIMITED_POWER_FEEDBACK_REGISTER, 2)
        out["limited_power_feedback_3044_3045"] = limited
        if limited.get("ok"):
            limited_w = _u16s_to_s32(limited["values"])
            out["limited_power_feedback_w"] = limited_w
            out["limited_power_feedback_kw"] = round(limited_w / 1000.0, 3)

        switch = client.read_input_u16s(SOLIS_POWER_LIMIT_SWITCH_FEEDBACK_REGISTER, 1)
        out["power_limit_switch_feedback_3089"] = switch
        if switch.get("ok"):
            out["power_limit_switch_raw"] = int(switch["values"][0])

        limiting = client.read_input_u16s(SOLIS_LIMITING_STATUS_REGISTER, 1)
        out["limiting_status_3094"] = limiting
        if limiting.get("ok"):
            out["limiting_status_raw"] = int(limiting["values"][0])

    return out


def _solis_power_feedback(client: Any, cfg: SolisConfig, expected_raw: int) -> dict[str, Any]:
    """Read the field-proven command/feedback chain after a 3051 change."""
    feedback = read_solis_status(client, cfg, extended=True)
    pct_raw = feedback.get("power_limit_feedback_raw")
    setting_raw = feedback.get("power_limit_percent_raw")
    expected_w = int(round(float(cfg.rated_power_kw) * 1000.0 * expected_raw / 10000.0))
    limited_w = feedback.get("limited_power_feedback_w")

    feedback["expected_power_limit_raw"] = int(expected_raw)
    feedback["expected_limited_power_w"] = expected_w
    feedback["setting_verified"] = setting_raw == expected_raw
    feedback["percentage_feedback_verified"] = pct_raw == expected_raw
    # Allow a small reporting tolerance on the derived kW feedback.
    feedback["limited_power_feedback_verified"] = (
        limited_w is not None and abs(int(limited_w) - expected_w) <= max(100, int(abs(expected_w) * 0.01))
    )
    feedback["verified"] = bool(
        feedback["setting_verified"] and feedback["percentage_feedback_verified"]
    )
    return feedback


def command_solis(
    client: Any,
    cfg: SolisConfig,
    target: str,
    *,
    derate_power_kw: float,
    live: bool,
    force: bool = False,
) -> dict[str, Any]:
    """Apply Solis ON/OFF plus field-validated active-power percentage control.

    For ON_NORMAL and ON_DERATED the active-power setpoint is prepared BEFORE an ON
    transition. This avoids briefly starting an inverter at the wrong power limit.
    Holding 3069 is only checked; it is intentionally not rewritten automatically.
    """
    if target == SOLAR_HOLD:
        return {"device": "Solis", "target": SOLAR_HOLD, "skipped": True, "reason": "hold_no_solar_command"}
    if not cfg.enabled:
        return {"device": "Solis", "enabled": False, "target": target, "skipped": True}
    if target not in {SOLAR_NORMAL, SOLAR_DERATED, SOLAR_OFF}:
        raise ValueError(f"Invalid Solis target={target}")
    if client is None:
        raise RuntimeError("Solis client not connected")

    if cfg.control_method not in {"holding_onoff_3006", "holding_onoff_3007"}:
        raise ValueError(
            "Field-validated Solis integration only permits holding register 3006 ON/OFF. "
            f"Unsupported control_method={cfg.control_method}"
        )

    writes: list[dict[str, Any]] = []

    # Solar OFF retains the previously field-validated ON/OFF implementation.
    if target == SOLAR_OFF:
        before = client.read_holding_u16(SOLIS_HOLDING_ON_OFF_REGISTER)
        if not before.get("ok"):
            if live:
                raise RuntimeError(
                    "Solis FC03 pre-read of holding register 3006 failed; refusing blind FC06 OFF write: "
                    f"{before}"
                )
            return {
                "device": "Solis", "target": target, "dry_run": True,
                "method": "raw_fc06_holding_3006_with_fc03_readback",
                "state_before": before, "warning": "pre_read_failed_no_write_in_dry_run",
            }
        if int(before.get("value")) == SOLIS_HOLDING_OFF_VALUE and not force:
            return {
                "device": "Solis", "target": target, "skipped": True,
                "reason": "already_in_target_state", "state_before": before,
            }
        if not live:
            return {
                "device": "Solis", "target": target, "dry_run": True,
                "method": "raw_fc06_holding_3006_with_fc03_readback",
                "send_address": SOLIS_HOLDING_ON_OFF_REGISTER,
                "value_hex": f"0x{SOLIS_HOLDING_OFF_VALUE:04X}", "state_before": before,
            }
        result = client.write_holding_u16_verified(
            SOLIS_HOLDING_ON_OFF_REGISTER, SOLIS_HOLDING_OFF_VALUE, retries=2
        )
        if not result.get("ok"):
            raise RuntimeError(
                f"Solis OFF FC06 write was not verified by FC03 readback on register {SOLIS_HOLDING_ON_OFF_REGISTER}: {result}"
            )
        writes.append({
            "kind": "on_off", "address": SOLIS_HOLDING_ON_OFF_REGISTER,
            "value": SOLIS_HOLDING_OFF_VALUE, "value_hex": f"0x{SOLIS_HOLDING_OFF_VALUE:04X}",
            "verified": True, "result": result,
        })
        return {
            "device": "Solis", "target": target, "dry_run": False,
            "method": "field_validated_solis_control", "writes": writes,
            "write_result": result,
        }

    desired_raw = (
        _percent_to_solis_raw(cfg.normal_power_percent)
        if target == SOLAR_NORMAL
        else _kw_to_solis_percent_raw(derate_power_kw, cfg.rated_power_kw)
    )
    desired_percent = desired_raw / 100.0
    desired_kw = float(cfg.rated_power_kw) * desired_raw / 10000.0

    current_limit = client.read_holding_u16(SOLIS_POWER_LIMIT_PERCENT_REGISTER)
    if not current_limit.get("ok"):
        if live:
            raise RuntimeError(
                f"Solis FC03 pre-read of holding register {SOLIS_POWER_LIMIT_PERCENT_REGISTER} failed; "
                f"refusing blind active-power write: {current_limit}"
            )
        return {
            "device": "Solis", "target": target, "dry_run": True,
            "desired_power_percent_raw": desired_raw, "desired_power_percent": desired_percent,
            "desired_power_kw": desired_kw, "power_limit_before": current_limit,
            "warning": "power_limit_pre_read_failed_no_write_in_dry_run",
        }

    current_raw = int(current_limit["value"])
    need_power_write = force or current_raw != desired_raw

    if need_power_write:
        enable = client.read_holding_u16(SOLIS_POWER_CONTROL_ENABLE_REGISTER)
        if not enable.get("ok"):
            if live:
                raise RuntimeError(
                    f"Solis FC03 pre-read of active-power enable register {SOLIS_POWER_CONTROL_ENABLE_REGISTER} failed; "
                    f"refusing blind power-limit write: {enable}"
                )
        elif int(enable.get("value")) != SOLIS_POWER_CONTROL_ENABLE_VALUE:
            raise RuntimeError(
                f"Solis active-power control is not enabled: register {SOLIS_POWER_CONTROL_ENABLE_REGISTER}="
                f"0x{int(enable.get('value')):04X}; expected 0x{SOLIS_POWER_CONTROL_ENABLE_VALUE:04X}. "
                "Controller will not modify this persistent setting automatically."
            )

        if not live:
            return {
                "device": "Solis", "target": target, "dry_run": True,
                "method": "fc06_holding_3051_percentage_with_fc03_readback",
                "send_address": SOLIS_POWER_LIMIT_PERCENT_REGISTER,
                "value": desired_raw, "desired_power_percent": desired_percent,
                "desired_power_kw": desired_kw, "power_limit_before": current_limit,
            }

        result = client.write_holding_u16_verified(
            SOLIS_POWER_LIMIT_PERCENT_REGISTER, desired_raw, retries=2
        )
        if not result.get("ok"):
            raise RuntimeError(
                f"Solis active-power FC06 write was not verified by FC03 readback on register "
                f"{SOLIS_POWER_LIMIT_PERCENT_REGISTER}: {result}"
            )
        feedback = _solis_power_feedback(client, cfg, desired_raw)
        writes.append({
            "kind": "active_power_percent", "address": SOLIS_POWER_LIMIT_PERCENT_REGISTER,
            "value": desired_raw, "percent": desired_percent, "equivalent_kw": desired_kw,
            "verified": bool(result.get("readback_verified")),
            "feedback_verified": bool(feedback.get("verified")),
            "result": result, "feedback": feedback,
        })

    # Ensure the inverter is ON after preparing the requested active-power ceiling.
    onoff = client.read_holding_u16(SOLIS_HOLDING_ON_OFF_REGISTER)
    if not onoff.get("ok"):
        if live:
            raise RuntimeError(
                "Solis FC03 pre-read of holding register 3006 failed; refusing blind FC06 ON write: "
                f"{onoff}"
            )
    else:
        need_on_write = force or int(onoff.get("value")) != SOLIS_HOLDING_ON_VALUE
        if need_on_write:
            if not live:
                return {
                    "device": "Solis", "target": target, "dry_run": True,
                    "desired_power_percent_raw": desired_raw, "desired_power_percent": desired_percent,
                    "desired_power_kw": desired_kw, "power_limit_before": current_limit,
                    "on_off_before": onoff,
                }
            result = client.write_holding_u16_verified(
                SOLIS_HOLDING_ON_OFF_REGISTER, SOLIS_HOLDING_ON_VALUE, retries=2
            )
            if not result.get("ok"):
                raise RuntimeError(
                    f"Solis ON FC06 write was not verified by FC03 readback on register {SOLIS_HOLDING_ON_OFF_REGISTER}: {result}"
                )
            writes.append({
                "kind": "on_off", "address": SOLIS_HOLDING_ON_OFF_REGISTER,
                "value": SOLIS_HOLDING_ON_VALUE, "value_hex": f"0x{SOLIS_HOLDING_ON_VALUE:04X}",
                "verified": True, "result": result,
            })

    if not writes:
        return {
            "device": "Solis", "target": target, "skipped": True,
            "reason": "already_in_target_power_mode_and_on",
            "desired_power_percent_raw": desired_raw, "desired_power_percent": desired_percent,
            "desired_power_kw": desired_kw, "power_limit_before": current_limit, "on_off_before": onoff,
        }

    return {
        "device": "Solis", "target": target, "dry_run": False,
        "method": "field_validated_solis_control", "writes": writes,
        "desired_power_percent_raw": desired_raw, "desired_power_percent": desired_percent,
        "desired_power_kw": desired_kw,
        "write_result": (writes[-1].get("result") if writes else None),
    }


def build_action_plan(previous_state: str, desired_bess: dict[str, str], desired_solar: str, solar_enabled: bool) -> list[tuple[str, str, str]]:
    """Build ordered action plan: (kind, key, target)."""
    plan: list[tuple[str, str, str]] = []

    if desired_solar == SOLAR_HOLD:
        if previous_state == STATE_X_LOW_CUTOFF:
            order = ["X", "Y"]
        elif previous_state == STATE_Y_LOW_CUTOFF:
            order = ["Y", "X"]
        else:
            order = ["X", "Y"]
        for key in order:
            if key in desired_bess:
                plan.append(("bess", key, desired_bess[key]))
        return plan

    # Preserve the validated safety ordering: when both BESS hit the OFF threshold,
    # switch solar OFF before re-enabling a BESS that was previously isolated.
    both_bess_on = desired_bess.get("X") == "ON" and desired_bess.get("Y") == "ON"
    both_high_target = desired_solar == SOLAR_OFF and both_bess_on
    if both_high_target:
        if solar_enabled:
            plan.append(("solar", "Solis", SOLAR_OFF))
        if previous_state == STATE_X_HIGH_ONLY:
            plan.append(("bess", "X", "ON"))
            plan.append(("bess", "Y", "ON"))
        elif previous_state == STATE_Y_HIGH_ONLY:
            plan.append(("bess", "Y", "ON"))
            plan.append(("bess", "X", "ON"))
        else:
            plan.append(("bess", "X", "ON"))
            plan.append(("bess", "Y", "ON"))
        return plan

    for key in ("X", "Y"):
        if key in desired_bess:
            plan.append(("bess", key, desired_bess[key]))
    if solar_enabled and desired_solar in {SOLAR_NORMAL, SOLAR_DERATED, SOLAR_OFF}:
        plan.append(("solar", "Solis", desired_solar))
    return plan


def build_operator_status(
    cycle: dict[str, Any],
    *,
    args: argparse.Namespace,
    version: str,
) -> dict[str, Any]:
    """Normalize a controller cycle into a stable, Flutter-friendly status object."""
    devices = cycle.get("devices") or {}
    controller = cycle.get("controller_state") or {}
    desired = cycle.get("desired_states") or {}
    solar = cycle.get("solar_status_after") or cycle.get("solar_status_before") or {}
    solis_state = solar.get("on_off_state")
    solis_power_w = solar.get("active_power_w")
    solis_online = bool(
        solar.get("enabled")
        and (solar.get("on_off_register_3006") or {}).get("ok")
        and (solar.get("active_power") or {}).get("ok")
    )

    action_results: list[dict[str, Any]] = []
    for action in cycle.get("actions") or []:
        item = {
            "device": action.get("device"),
            "target": action.get("target"),
            "skipped": bool(action.get("skipped", False)),
            "reason": action.get("reason"),
            "dry_run": bool(action.get("dry_run", False)),
        }
        if action.get("device") == "Solis":
            writes = action.get("writes") or []
            item["verified"] = bool(
                action.get("skipped")
                or not args.live
                or (writes and all(bool(w.get("verified")) for w in writes))
            )
        else:
            writes = action.get("writes") or []
            item["verified"] = bool(
                action.get("skipped")
                or not args.live
                or (writes and all(bool(w.get("readback_verified", not args.no_readback)) for w in writes))
            )
        action_results.append(item)

    status = {
        "available": True,
        "timestamp_utc": cycle.get("timestamp_utc") or utc_now(),
        "version": version,
        "mode": "LIVE" if args.live else "DRY_RUN",
        "healthy": "error" not in cycle,
        "error": cycle.get("error"),
        "controller": {
            "state": controller.get("next") or controller.get("previous") or STATE_NORMAL,
            "previous_state": controller.get("previous"),
            "decision": cycle.get("decision"),
            "solar_off_reason": controller.get("solar_off_reason"),
            "low_cutoff_reason": controller.get("low_cutoff_reason"),
            "trend": controller.get("trend") or {},
        },
        "thresholds": {
            "derate_soc_percent": float((cycle.get("control_settings") or {}).get("derate_soc_limit", args.derate_soc_limit)),
            "derate_power_kw": float((cycle.get("control_settings") or {}).get("derate_power_kw", args.derate_power_kw)),
            "high_soc_percent": float((cycle.get("control_settings") or {}).get("high_limit", args.high_limit)),
            "recovery_soc_percent": float((cycle.get("control_settings") or {}).get("recovery_limit", args.recovery_limit)),
            "low_cutoff_enabled": bool(args.low_cutoff_enable),
            "low_cutoff_percent": float((cycle.get("control_settings") or {}).get("low_cutoff_limit", args.low_cutoff_limit)),
            "low_recovery_percent": float((cycle.get("control_settings") or {}).get("low_recovery_limit", args.low_recovery_limit)),
            "settings_revision": cycle.get("control_settings_revision"),
            "settings_updated_at_utc": cycle.get("control_settings_updated_at_utc"),
            "settings_updated_by": cycle.get("control_settings_updated_by"),
        },
        "bess": {
            key: {
                "host": (devices.get(key) or {}).get("host"),
                "soc_percent": (devices.get(key) or {}).get("soc"),
                "online": bool((devices.get(key) or {}).get("online", False)),
                "target_state": (desired.get("bess") or {}).get(key),
            }
            for key in ("X", "Y")
        },
        "solis": {
            "enabled": bool(args.solar_enable),
            "online": solis_online,
            "state": solis_state,
            # Keep legacy ON/OFF target_state compatible with the existing Flutter UI.
            "target_state": (
                "ON" if desired.get("solar") in {SOLAR_NORMAL, SOLAR_DERATED}
                else "OFF" if desired.get("solar") == SOLAR_OFF
                else SOLAR_HOLD
            ),
            "power_mode": (
                "DERATED" if desired.get("solar") == SOLAR_DERATED
                else "NORMAL" if desired.get("solar") == SOLAR_NORMAL
                else "OFF" if desired.get("solar") == SOLAR_OFF
                else "HOLD"
            ),
            "target_power_kw": (
                float((cycle.get("control_settings") or {}).get("derate_power_kw", args.derate_power_kw))
                if desired.get("solar") == SOLAR_DERATED else None
            ),
            "active_power_w": solis_power_w,
            "active_power_kw": round(float(solis_power_w) / 1000.0, 3) if solis_power_w is not None else None,
            "power_limit_percent_raw": solar.get("power_limit_percent_raw"),
            "power_limit_percent": solar.get("power_limit_percent"),
            "power_limit_feedback_raw": solar.get("power_limit_feedback_raw"),
            "power_limit_feedback_percent": solar.get("power_limit_feedback_percent"),
            "power_limit_equivalent_kw": solar.get("power_limit_equivalent_kw"),
            "limited_power_feedback_w": solar.get("limited_power_feedback_w"),
            "limiting_status_raw": solar.get("limiting_status_raw"),
            "serial_port": args.solis_serial_port,
            "unit_id": int(args.solis_unit_id),
        },
        "last_actions": action_results,
        "action_plan": cycle.get("action_plan") or [],
    }
    return status


def monitor_append_event_safe(monitor: Any, **kwargs: Any) -> None:
    if monitor is None:
        return
    try:
        monitor.append_event(**kwargs)
    except Exception as exc:
        print(json.dumps({
            "timestamp_utc": utc_now(),
            "event": "operator_monitor_event_write_failed",
            "error": str(exc),
        }), file=sys.stderr, flush=True)


def persist_operator_cycle(
    monitor: Any,
    cycle: dict[str, Any],
    *,
    args: argparse.Namespace,
    version: str,
) -> None:
    """Persist current state every cycle and only meaningful history events."""
    if monitor is None:
        return
    try:
        previous = monitor.read_status()
        status = build_operator_status(cycle, args=args, version=version)
        monitor.write_status(status)

        ctrl = status["controller"]
        bx = status["bess"]["X"]
        by = status["bess"]["Y"]
        solis = status["solis"]
        common = {
            "controller_state": ctrl.get("state"),
            "decision": ctrl.get("decision"),
            "soc_x": bx.get("soc_percent"),
            "soc_y": by.get("soc_percent"),
            "solis_state": solis.get("state"),
            "solis_power_w": solis.get("active_power_w"),
            "timestamp_utc": status.get("timestamp_utc"),
        }

        if cycle.get("error"):
            monitor_append_event_safe(
                monitor,
                event_type="controller_cycle_error",
                severity="error",
                result="failed",
                message=f"SOC/Solis controller cycle failed: {cycle['error']}",
                payload={"error": cycle.get("error")},
                **common,
            )
            return

        previous_available = bool(previous.get("available"))
        prev_ctrl = (previous.get("controller") or {}) if previous_available else {}
        prev_solis = (previous.get("solis") or {}) if previous_available else {}
        prev_bess = (previous.get("bess") or {}) if previous_available else {}

        if not previous_available:
            monitor_append_event_safe(
                monitor,
                event_type="controller_snapshot_initialized",
                message="Operator controller status initialized",
                result="success",
                payload={"mode": status.get("mode")},
                **common,
            )
        elif prev_ctrl.get("state") != ctrl.get("state"):
            monitor_append_event_safe(
                monitor,
                event_type="controller_state_transition",
                message=f"Controller state changed from {prev_ctrl.get('state')} to {ctrl.get('state')}",
                result="success",
                payload={
                    "from_state": prev_ctrl.get("state"),
                    "to_state": ctrl.get("state"),
                    "solar_off_reason": ctrl.get("solar_off_reason"),
                },
                **common,
            )

        if previous_available and prev_ctrl.get("decision") != ctrl.get("decision"):
            monitor_append_event_safe(
                monitor,
                event_type="controller_decision_changed",
                message=f"Controller decision changed to {ctrl.get('decision')}",
                result="success",
                payload={
                    "from_decision": prev_ctrl.get("decision"),
                    "to_decision": ctrl.get("decision"),
                },
                **common,
            )

        for action in cycle.get("actions") or []:
            if action.get("skipped") or action.get("dry_run"):
                continue
            device = str(action.get("device") or "unknown")
            target = action.get("target")
            if device == "Solis":
                writes = action.get("writes") or []
                verified = bool(writes and all(bool(w.get("verified")) for w in writes))
                monitor_append_event_safe(
                    monitor,
                    event_type="solis_command",
                    device="Solis",
                    target=target,
                    result="success" if verified else "failed",
                    severity="info" if verified else "error",
                    message=f"Solis command {target} {'verified' if verified else 'failed verification'}",
                    payload={
                        "method": action.get("method"),
                        "desired_power_percent_raw": action.get("desired_power_percent_raw"),
                        "desired_power_percent": action.get("desired_power_percent"),
                        "desired_power_kw": action.get("desired_power_kw"),
                        "writes": writes,
                    },
                    **common,
                )
            else:
                writes = action.get("writes") or []
                verified = bool(writes and all(bool(w.get("readback_verified", not args.no_readback)) for w in writes))
                monitor_append_event_safe(
                    monitor,
                    event_type="bess_command",
                    device=device,
                    target=target,
                    result="success" if verified else "failed",
                    severity="info" if verified else "error",
                    message=f"BESS {device} command {target} {'verified' if verified else 'failed verification'}",
                    payload={"writes": writes},
                    **common,
                )

        if previous_available and prev_solis.get("power_mode") != solis.get("power_mode"):
            monitor_append_event_safe(
                monitor,
                event_type="solis_power_mode_changed",
                device="Solis",
                target=solis.get("power_mode"),
                result="observed",
                message=f"Solis power mode changed from {prev_solis.get('power_mode')} to {solis.get('power_mode')}",
                payload={
                    "from_power_mode": prev_solis.get("power_mode"),
                    "to_power_mode": solis.get("power_mode"),
                    "target_power_kw": solis.get("target_power_kw"),
                    "power_limit_percent": solis.get("power_limit_percent"),
                },
                **common,
            )

        if previous_available and prev_solis.get("state") != solis.get("state"):
            monitor_append_event_safe(
                monitor,
                event_type="solis_state_changed",
                device="Solis",
                target=solis.get("state"),
                result="observed",
                message=f"Observed Solis state changed from {prev_solis.get('state')} to {solis.get('state')}",
                payload={
                    "from_state": prev_solis.get("state"),
                    "to_state": solis.get("state"),
                },
                **common,
            )

        for device in ("X", "Y"):
            old_online = ((prev_bess.get(device) or {}).get("online") if previous_available else None)
            new_online = (status["bess"][device] or {}).get("online")
            if old_online is not None and old_online != new_online:
                monitor_append_event_safe(
                    monitor,
                    event_type="communication_restored" if new_online else "communication_lost",
                    severity="info" if new_online else "warning",
                    device=device,
                    result="online" if new_online else "offline",
                    message=f"BESS {device} communication {'restored' if new_online else 'lost'}",
                    payload={},
                    **common,
                )

        old_solis_online = prev_solis.get("online") if previous_available else None
        new_solis_online = solis.get("online")
        if old_solis_online is not None and old_solis_online != new_solis_online:
            monitor_append_event_safe(
                monitor,
                event_type="communication_restored" if new_solis_online else "communication_lost",
                severity="info" if new_solis_online else "warning",
                device="Solis",
                result="online" if new_solis_online else "offline",
                message=f"Solis communication {'restored' if new_solis_online else 'lost'}",
                payload={},
                **common,
            )
    except Exception as exc:
        print(json.dumps({
            "timestamp_utc": utc_now(),
            "event": "operator_monitor_cycle_persist_failed",
            "error": str(exc),
        }), file=sys.stderr, flush=True)


def config_to_arg_defaults(path: str | None) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "x_host": "192.168.100.151",
        "y_host": "192.168.100.153",
        "port": 502,
        "unit_id": 1,
        "byte_order": "ABCD",
        "derate_soc_limit": 90.0,
        "derate_power_kw": 20.0,
        "high_limit": 98.0,
        "recovery_limit": 75.0,
        "low_cutoff_enabled": False,
        "low_cutoff_limit": 10.0,
        "low_recovery_limit": 10.0,
        "soc_trend_window_sec": 60.0,
        "soc_trend_negative_delta": 0.1,
        "state_file": "/tmp/nb_ems_soc_solis_controller_state.json",
        "interval": 5.0,
        "timeout": 3.0,
        "once": False,
        "live": False,
        "force": False,
        "no_readback": False,
        "enable_reset_before_on": False,
        "enable_offgrid_before_on": False,
        "inter_device_command_delay_sec": 2.0,
        "solar_enable": False,
        "solis_transport": "rtu",
        "solis_serial_port": "/dev/ems_solis_rtu",
        "solis_baudrate": 9600,
        "solis_unit_id": 1,
        "solis_timeout": 3.0,
        "solis_control_method": "holding_onoff_3006",
        "solis_rated_power_kw": 100.0,
        "solis_normal_power_percent": 110.0,
        "no_solis_status_read": False,
        "operator_monitor_enabled": True,
        "operator_status_path": "/var/lib/nb-ems-soc-solis-controller/operator_status.json",
        "operator_history_db_path": "/var/lib/nb-ems-soc-solis-controller/operator_history.db",
        "operator_retention_days": 30,
        "operator_max_events": 20000,
        "controller_settings_enabled": True,
        "controller_settings_path": "/var/lib/nb-ems-soc-solis-controller/control_settings.json",
    }
    if not path:
        return defaults
    data = json.loads(Path(path).read_text())

    ems = data.get("ems", {})
    x = ems.get("x", {})
    y = ems.get("y", {})
    defaults["x_host"] = x.get("host", defaults["x_host"])
    defaults["y_host"] = y.get("host", defaults["y_host"])
    defaults["port"] = int(x.get("port", y.get("port", defaults["port"])))
    defaults["unit_id"] = int(x.get("unit_id", y.get("unit_id", defaults["unit_id"])))

    solis = data.get("solis", {})
    defaults["solar_enable"] = bool(solis.get("enabled", defaults["solar_enable"]))
    defaults["solis_transport"] = solis.get("transport", defaults["solis_transport"])
    defaults["solis_serial_port"] = solis.get("serial_port", defaults["solis_serial_port"])
    defaults["solis_baudrate"] = int(solis.get("baudrate", defaults["solis_baudrate"]))
    defaults["solis_unit_id"] = int(solis.get("unit_id", defaults["solis_unit_id"]))
    defaults["solis_timeout"] = float(solis.get("timeout", defaults["solis_timeout"]))
    defaults["solis_control_method"] = solis.get("control_method", defaults["solis_control_method"])
    defaults["solis_rated_power_kw"] = float(solis.get("rated_power_kw", defaults["solis_rated_power_kw"]))
    defaults["solis_normal_power_percent"] = float(solis.get("normal_power_percent", defaults["solis_normal_power_percent"]))
    defaults["no_solis_status_read"] = not bool(solis.get("status_read_enabled", not defaults["no_solis_status_read"]))

    soc_logic = data.get("soc_logic", {})
    defaults["derate_soc_limit"] = float(soc_logic.get("derate_soc_limit", defaults["derate_soc_limit"]))
    defaults["derate_power_kw"] = float(soc_logic.get("derate_power_kw", defaults["derate_power_kw"]))
    defaults["high_limit"] = float(soc_logic.get("high_limit", defaults["high_limit"]))
    defaults["recovery_limit"] = float(soc_logic.get("recovery_limit", defaults["recovery_limit"]))
    low_enabled = bool(soc_logic.get("low_cutoff_enabled", defaults["low_cutoff_enabled"]))
    low_enabled = low_enabled or bool(soc_logic.get("enable_low_cutoff", False))
    low_enabled = low_enabled or bool(soc_logic.get("low_logic_enabled", False))
    defaults["low_cutoff_enabled"] = low_enabled
    defaults["low_cutoff_limit"] = float(soc_logic.get("low_cutoff_limit", defaults["low_cutoff_limit"]))
    defaults["low_recovery_limit"] = float(soc_logic.get("low_recovery_limit", soc_logic.get("low_cutoff_limit", defaults["low_recovery_limit"])))
    defaults["soc_trend_window_sec"] = float(soc_logic.get("soc_trend_window_sec", defaults["soc_trend_window_sec"]))
    defaults["soc_trend_negative_delta"] = float(soc_logic.get("soc_trend_negative_delta", defaults["soc_trend_negative_delta"]))
    defaults["state_file"] = soc_logic.get("state_file", defaults["state_file"])

    control = data.get("control", {})
    defaults["interval"] = float(control.get("interval_sec", defaults["interval"]))
    defaults["byte_order"] = control.get("byte_order", defaults["byte_order"])
    defaults["live"] = bool(control.get("live_default", defaults["live"]))
    defaults["force"] = bool(control.get("force_default", defaults["force"]))
    defaults["once"] = bool(control.get("once_default", defaults["once"]))
    defaults["no_readback"] = not bool(control.get("readback", not defaults["no_readback"]))
    defaults["enable_reset_before_on"] = bool(control.get("enable_reset_before_on", defaults["enable_reset_before_on"]))
    defaults["enable_offgrid_before_on"] = bool(control.get("enable_offgrid_before_on", defaults["enable_offgrid_before_on"]))
    defaults["inter_device_command_delay_sec"] = float(control.get("inter_device_command_delay_sec", defaults["inter_device_command_delay_sec"]))

    operator_monitor = data.get("operator_monitor", {})
    defaults["operator_monitor_enabled"] = bool(operator_monitor.get("enabled", defaults["operator_monitor_enabled"]))
    defaults["operator_status_path"] = operator_monitor.get("status_path", defaults["operator_status_path"])
    defaults["operator_history_db_path"] = operator_monitor.get("history_db_path", defaults["operator_history_db_path"])
    defaults["operator_retention_days"] = int(operator_monitor.get("retention_days", defaults["operator_retention_days"]))
    defaults["operator_max_events"] = int(operator_monitor.get("max_events", defaults["operator_max_events"]))

    controller_settings = data.get("controller_settings", {})
    defaults["controller_settings_enabled"] = bool(controller_settings.get("enabled", defaults["controller_settings_enabled"]))
    defaults["controller_settings_path"] = controller_settings.get("path", defaults["controller_settings_path"])
    return defaults


def parse_args() -> argparse.Namespace:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", default=None, help="JSON config file for EMS, Solis RTU, SOC limits, and controller settings")
    pre_args, remaining = pre.parse_known_args()
    d = config_to_arg_defaults(pre_args.config)

    p = argparse.ArgumentParser(description="SOC EMS X/Y BESS controller with transition-aware Solis RTU solar control", parents=[pre])
    p.add_argument("--x-host", default=d["x_host"], help="BESS/EMS X Modbus TCP IP")
    p.add_argument("--y-host", default=d["y_host"], help="BESS/EMS Y Modbus TCP IP")
    p.add_argument("--port", type=int, default=d["port"])
    p.add_argument("--unit-id", type=int, default=d["unit_id"])
    p.add_argument("--byte-order", default=d["byte_order"], choices=["ABCD", "BADC", "CDAB", "DCBA"])
    p.add_argument("--derate-soc-limit", type=float, default=d["derate_soc_limit"], help="Both BESS strictly above this SOC enter solar derating")
    p.add_argument("--derate-power-kw", type=float, default=d["derate_power_kw"], help="Solar active-power target during derating")
    p.add_argument("--high-limit", type=float, default=d["high_limit"])
    p.add_argument("--recovery-limit", type=float, default=d["recovery_limit"])
    p.add_argument("--low-cutoff-enable", action=argparse.BooleanOptionalAction, default=d["low_cutoff_enabled"], help="Enable lower SOC cutoff protection")
    p.add_argument("--low-cutoff-limit", type=float, default=d["low_cutoff_limit"])
    p.add_argument("--low-recovery-limit", type=float, default=d["low_recovery_limit"], help="SOC threshold for clearing a latched low-cutoff state")
    p.add_argument("--soc-trend-window-sec", type=float, default=d["soc_trend_window_sec"])
    p.add_argument("--soc-trend-negative-delta", type=float, default=d["soc_trend_negative_delta"])
    p.add_argument("--state-file", default=d["state_file"])
    p.add_argument("--clear-state", action="store_true")
    p.add_argument("--interval", type=float, default=d["interval"], help="Loop interval seconds")
    p.add_argument("--timeout", type=float, default=d["timeout"])
    p.add_argument("--once", action=argparse.BooleanOptionalAction, default=d["once"], help="Run only one control cycle")
    p.add_argument("--live", action=argparse.BooleanOptionalAction, default=d["live"], help="Actually write Modbus commands. Default config is dry-run.")
    p.add_argument("--force", action=argparse.BooleanOptionalAction, default=d["force"], help="Send command even if target state already commanded")
    p.add_argument("--no-readback", action="store_true", default=d["no_readback"])
    p.add_argument("--enable-reset-before-on", action=argparse.BooleanOptionalAction, default=d["enable_reset_before_on"])
    p.add_argument("--enable-offgrid-before-on", action=argparse.BooleanOptionalAction, default=d["enable_offgrid_before_on"])
    p.add_argument("--inter-device-command-delay-sec", type=float, default=d["inter_device_command_delay_sec"], help="Delay between sequential BESS/Solis transition commands")
    p.add_argument("--solar-enable", action=argparse.BooleanOptionalAction, default=d["solar_enable"], help="Enable Solis solar read/control integration")
    p.add_argument("--solis-transport", choices=["rtu"], default=d["solis_transport"])
    p.add_argument("--solis-serial-port", default=d["solis_serial_port"])
    p.add_argument("--solis-baudrate", type=int, default=d["solis_baudrate"])
    p.add_argument("--solis-unit-id", type=int, default=d["solis_unit_id"])
    p.add_argument("--solis-timeout", type=float, default=d["solis_timeout"])
    p.add_argument("--solis-control-method", choices=["holding_onoff_3006", "holding_onoff_3007"], default=d["solis_control_method"])
    p.add_argument("--solis-rated-power-kw", type=float, default=d["solis_rated_power_kw"], help="Rated active-power base used to convert kW derate target to register 3051 percentage")
    p.add_argument("--solis-normal-power-percent", type=float, default=d["solis_normal_power_percent"], help="Normal/unrestricted register 3051 setting; field baseline is 110 percent")
    p.add_argument("--no-solis-status-read", action="store_true", default=d["no_solis_status_read"])
    p.add_argument("--operator-monitor-enable", action=argparse.BooleanOptionalAction, default=d["operator_monitor_enabled"], help="Publish operator status/history for the gateway API")
    p.add_argument("--operator-status-path", default=d["operator_status_path"])
    p.add_argument("--operator-history-db-path", default=d["operator_history_db_path"])
    p.add_argument("--operator-retention-days", type=int, default=d["operator_retention_days"])
    p.add_argument("--operator-max-events", type=int, default=d["operator_max_events"])
    p.add_argument("--controller-settings-enable", action=argparse.BooleanOptionalAction, default=d["controller_settings_enabled"], help="Reload admin-configurable SOC thresholds each cycle")
    p.add_argument("--controller-settings-path", default=d["controller_settings_path"], help="Persistent runtime SOC threshold settings file")
    return p.parse_args(remaining)


def sleep_between_actions(seconds: float, *, action_index: int, action_total: int) -> None:
    if action_index < action_total - 1 and seconds > 0:
        time.sleep(seconds)


def main() -> int:
    global _stop
    args = parse_args()
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    controller_state_store = load_controller_state(args.state_file, clear=args.clear_state)
    version = "v1.14_soc_solar_derate_90_98"

    monitor = None
    if args.operator_monitor_enable:
        if ControllerMonitorStore is None:
            print(json.dumps({
                "timestamp_utc": utc_now(),
                "event": "operator_monitor_disabled_import_error",
                "error": _MONITOR_IMPORT_ERROR,
            }), file=sys.stderr, flush=True)
        else:
            try:
                monitor = ControllerMonitorStore(
                    status_path=args.operator_status_path,
                    history_db_path=args.operator_history_db_path,
                )
                monitor.cleanup(
                    retention_days=args.operator_retention_days,
                    max_events=args.operator_max_events,
                )
            except Exception as exc:
                monitor = None
                print(json.dumps({
                    "timestamp_utc": utc_now(),
                    "event": "operator_monitor_init_failed",
                    "error": str(exc),
                }), file=sys.stderr, flush=True)

    static_control_settings = {
        "derate_soc_limit": float(args.derate_soc_limit),
        "derate_power_kw": float(args.derate_power_kw),
        "high_limit": float(args.high_limit),
        "recovery_limit": float(args.recovery_limit),
        "low_cutoff_limit": float(args.low_cutoff_limit),
        "low_recovery_limit": float(args.low_recovery_limit),
    }
    effective_control_settings = dict(static_control_settings)
    control_settings_meta: dict[str, Any] = {
        "revision": None,
        "updated_at_utc": None,
        "updated_by": "config_defaults",
    }
    controller_settings_store = None
    if args.controller_settings_enable:
        if ControllerSettingsStore is None:
            print(json.dumps({
                "timestamp_utc": utc_now(),
                "event": "controller_settings_disabled_import_error",
                "error": _SETTINGS_IMPORT_ERROR,
            }), file=sys.stderr, flush=True)
        else:
            try:
                controller_settings_store = ControllerSettingsStore(path=args.controller_settings_path)
                settings_doc = controller_settings_store.ensure(static_control_settings)
                effective_control_settings = dict(settings_doc["settings"])
                control_settings_meta = {
                    "revision": settings_doc.get("revision"),
                    "updated_at_utc": settings_doc.get("updated_at_utc"),
                    "updated_by": settings_doc.get("updated_by"),
                }
            except Exception as exc:
                controller_settings_store = None
                print(json.dumps({
                    "timestamp_utc": utc_now(),
                    "event": "controller_settings_init_failed_using_config_defaults",
                    "settings_path": args.controller_settings_path,
                    "error": str(exc),
                }), file=sys.stderr, flush=True)

    x = EMSDevice("X", args.x_host, args.port, args.unit_id)
    y = EMSDevice("Y", args.y_host, args.port, args.unit_id)
    devices = {
        "X": EMSRuntime(x, make_ems_client(x, args.timeout)),
        "Y": EMSRuntime(y, make_ems_client(y, args.timeout)),
    }
    solis_cfg = SolisConfig(
        enabled=bool(args.solar_enable),
        transport=args.solis_transport,
        serial_port=args.solis_serial_port,
        baudrate=args.solis_baudrate,
        unit_id=args.solis_unit_id,
        timeout=args.solis_timeout,
        control_method=args.solis_control_method,
        status_read_enabled=not args.no_solis_status_read,
        rated_power_kw=float(args.solis_rated_power_kw),
        normal_power_percent=float(args.solis_normal_power_percent),
    )
    solis_client = make_solis_client(solis_cfg) if solis_cfg.enabled else None

    print(json.dumps({
        "timestamp_utc": utc_now(),
        "event": "soc_solis_controller_started",
        "version": version,
        "mode": "LIVE_WRITES_ENABLED" if args.live else "DRY_RUN_NO_WRITES",
        "derate_soc_limit": effective_control_settings["derate_soc_limit"],
        "derate_power_kw": effective_control_settings["derate_power_kw"],
        "high_limit": effective_control_settings["high_limit"],
        "recovery_limit": effective_control_settings["recovery_limit"],
        "low_cutoff_enabled": args.low_cutoff_enable,
        "low_cutoff_limit": effective_control_settings["low_cutoff_limit"],
        "low_recovery_limit": effective_control_settings["low_recovery_limit"],
        "soc_trend_window_sec": args.soc_trend_window_sec,
        "soc_trend_negative_delta": args.soc_trend_negative_delta,
        "state_file": args.state_file,
        "state_before_start": {k: v for k, v in controller_state_store.items() if k != "soc_history"},
        "x_host": args.x_host,
        "y_host": args.y_host,
        "inter_device_command_delay_sec": args.inter_device_command_delay_sec,
        "solar": {
            "enabled": solis_cfg.enabled,
            "transport": solis_cfg.transport,
            "serial_port": solis_cfg.serial_port,
            "baudrate": solis_cfg.baudrate,
            "unit_id": solis_cfg.unit_id,
            "control_method": solis_cfg.control_method,
            "rated_power_kw": solis_cfg.rated_power_kw,
            "normal_power_percent": solis_cfg.normal_power_percent,
        },
        "optional_reset_before_on": args.enable_reset_before_on,
        "optional_offgrid_before_on": args.enable_offgrid_before_on,
        "operator_monitor": {
            "enabled": monitor is not None,
            "status_path": args.operator_status_path,
            "history_db_path": args.operator_history_db_path,
        },
        "controller_settings": {
            "enabled": controller_settings_store is not None,
            "path": args.controller_settings_path,
            "revision": control_settings_meta.get("revision"),
            "updated_at_utc": control_settings_meta.get("updated_at_utc"),
            "updated_by": control_settings_meta.get("updated_by"),
            "effective_values": effective_control_settings,
            "reload": "each_control_cycle",
        },
    }, indent=2))

    monitor_append_event_safe(
        monitor,
        event_type="controller_started",
        message="SOC/Solis automatic controller started",
        result="running",
        payload={
            "version": version,
            "mode": "LIVE" if args.live else "DRY_RUN",
            "derate_soc_limit": effective_control_settings["derate_soc_limit"],
            "derate_power_kw": effective_control_settings["derate_power_kw"],
            "high_limit": effective_control_settings["high_limit"],
            "recovery_limit": effective_control_settings["recovery_limit"],
            "settings_revision": control_settings_meta.get("revision"),
        },
    )

    try:
        while not _stop:
            cycle: dict[str, Any] = {"timestamp_utc": utc_now(), "live": bool(args.live), "devices": {}, "actions": []}
            try:
                if controller_settings_store is not None:
                    try:
                        settings_doc = controller_settings_store.read()
                        effective_control_settings = dict(settings_doc["settings"])
                        control_settings_meta = {
                            "revision": settings_doc.get("revision"),
                            "updated_at_utc": settings_doc.get("updated_at_utc"),
                            "updated_by": settings_doc.get("updated_by"),
                        }
                    except Exception as settings_exc:
                        # Keep the last validated values rather than interrupting control.
                        cycle["controller_settings_warning"] = str(settings_exc)

                cycle["control_settings"] = dict(effective_control_settings)
                cycle["control_settings_revision"] = control_settings_meta.get("revision")
                cycle["control_settings_updated_at_utc"] = control_settings_meta.get("updated_at_utc")
                cycle["control_settings_updated_by"] = control_settings_meta.get("updated_by")

                for key, rt in devices.items():
                    rt.soc = read_ems_float(rt.client, REG_SOC, rt.device.unit_id, args.byte_order)
                    rt.online = True
                    rt.last_error = None
                    cycle["devices"][key] = {"host": rt.device.host, "soc": rt.soc, "online": True}

                if solis_cfg.enabled and solis_client is not None:
                    cycle["solar_status_before"] = read_solis_status(solis_client, solis_cfg)

                trend = update_soc_history(controller_state_store, devices["X"].soc, devices["Y"].soc, window_sec=args.soc_trend_window_sec)  # type: ignore[arg-type]
                previous_state = str(controller_state_store.get("state", STATE_NORMAL))
                decision, desired_bess, desired_solar, next_state, solar_off_reason, low_cutoff_reason, info = decide_states(
                    float(devices["X"].soc),
                    float(devices["Y"].soc),
                    effective_control_settings["high_limit"],
                    effective_control_settings["recovery_limit"],
                    effective_control_settings["low_cutoff_limit"],
                    derate_soc_limit=effective_control_settings["derate_soc_limit"],
                    low_cutoff_enabled=args.low_cutoff_enable,
                    low_recovery_limit=effective_control_settings["low_recovery_limit"],
                    controller_state=previous_state,
                    avg_soc_delta=trend.get("avg_soc_delta"),
                    trend_negative_delta=args.soc_trend_negative_delta,
                )

                plan = build_action_plan(previous_state, desired_bess, desired_solar, solis_cfg.enabled)
                cycle["decision"] = decision
                cycle["controller_state"] = {
                    "previous": previous_state,
                    "next": next_state,
                    "solar_off_reason": solar_off_reason,
                    "low_cutoff_reason": low_cutoff_reason,
                    "state_file": args.state_file,
                    "trend": trend,
                    "decision_info": info,
                }
                cycle["desired_states"] = {"bess": desired_bess, "solar": desired_solar}
                cycle["action_plan"] = [{"kind": k, "id": i, "target": t} for k, i, t in plan]

                for idx, (kind, key, target) in enumerate(plan):
                    if kind == "solar":
                        action = command_solis(
                            solis_client, solis_cfg, target,
                            derate_power_kw=effective_control_settings["derate_power_kw"],
                            live=args.live, force=args.force,
                        )  # type: ignore[arg-type]
                    else:
                        action = command_bess(
                            devices[key],
                            target,
                            live=args.live,
                            byte_order=args.byte_order,
                            readback=not args.no_readback,
                            force=args.force,
                            enable_reset_before_on=args.enable_reset_before_on,
                            enable_offgrid_before_on=args.enable_offgrid_before_on,
                        )
                    cycle["actions"].append(action)
                    sleep_between_actions(args.inter_device_command_delay_sec, action_index=idx, action_total=len(plan))

                # If a real Solis write occurred, capture the verified post-action state
                # immediately so the operator API does not show the pre-command state
                # until the next five-second cycle.
                solis_write_happened = any(
                    a.get("device") == "Solis"
                    and not a.get("skipped")
                    and not a.get("dry_run")
                    for a in cycle["actions"]
                )
                if solis_cfg.enabled and solis_client is not None and solis_write_happened:
                    cycle["solar_status_after"] = read_solis_status(solis_client, solis_cfg, extended=True)

                controller_state_store["state"] = next_state
                controller_state_store["solar_off_reason"] = solar_off_reason
                controller_state_store["low_cutoff_reason"] = low_cutoff_reason
                controller_state_store["last_decision"] = decision
                controller_state_store["last_update_utc"] = utc_now()
                controller_state_store["last_soc_x"] = devices["X"].soc
                controller_state_store["last_soc_y"] = devices["Y"].soc
                save_controller_state(args.state_file, controller_state_store)

            except Exception as exc:
                cycle["error"] = str(exc)
                persist_operator_cycle(monitor, cycle, args=args, version=version)
                print(json.dumps(cycle, indent=2), flush=True)
                if args.once:
                    return 2
            else:
                persist_operator_cycle(monitor, cycle, args=args, version=version)
                print(json.dumps(cycle, indent=2), flush=True)

            if args.once:
                break
            time.sleep(max(1.0, args.interval))
    finally:
        for rt in devices.values():
            try:
                rt.client.close()
            except Exception:
                pass
        if solis_client is not None:
            try:
                solis_client.close()
            except Exception:
                pass
        monitor_append_event_safe(
            monitor,
            event_type="controller_stopped",
            message="SOC/Solis automatic controller stopped",
            result="stopped",
            payload={"version": version},
        )
        print(json.dumps({"timestamp_utc": utc_now(), "event": "soc_solis_controller_stopped"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
