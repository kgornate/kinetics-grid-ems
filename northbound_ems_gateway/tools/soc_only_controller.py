#!/usr/bin/env python3
"""SOC field controller for two Chinese EMS/BESS units with optional Solis RTU solar control.

Confirmed BESS commands:
- BESS ON  = Manual Mode + Standby  (manual_auto_mode=0, manual_mode_control=2)
- BESS OFF = Manual Mode + Shutdown (manual_auto_mode=0, manual_mode_control=1)

v1.8 field change:
- Transition-aware sequencing for the one-high -> both-high case.
- If one BESS was OFF because it was high, and then both BESS become high, the controller
  sends Solar OFF first, then brings the previously OFF BESS back ON. This avoids a
  transient path where both BESS are OFF or both need to be started together.

Default mode is dry-run. Use --live --force only after validating decisions.
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
    control_method: str = "holding_onoff_3007"
    status_read_enabled: bool = True


# Chinese EMS / Unity261PV confirmed registers, Float32 encoded.
REG_MANUAL_AUTO_MODE = 10          # 0=Manual, 1=Auto
REG_MANUAL_MODE_CONTROL = 12       # 1=Shutdown/OFF, 2=Standby/ON, 3=Charge, 4=Discharge
REG_SOC = 80                       # SOC %, Float32

# Optional future BESS registers. Disabled by default in field config.
REG_ON_OFF_GRID_SWITCHING = 164    # 1=Grid-tied, 2=Off-grid
REG_SYSTEM_FAULT_RESET = 2704      # 0=Normal, 1=Reset. Some units reject this.

# Solis RTU commands from Solis protocol.
SOLIS_COIL_GRID_ON_OFF_5000 = 5000
SOLIS_HOLDING_ON_OFF_REGISTER_3007_SEND_ADDRESS = 3006  # document register 3007 with -1 offset
SOLIS_HOLDING_ON_VALUE = 0x00BE
SOLIS_HOLDING_OFF_VALUE = 0x00DE
SOLIS_POWER_LIMIT_SWITCH_3070_SEND_ADDRESS = 3069
SOLIS_POWER_LIMIT_VALUE_3052_SEND_ADDRESS = 3051

STATE_NORMAL = "NORMAL"
STATE_X_HIGH_ONLY = "X_HIGH_ONLY"
STATE_Y_HIGH_ONLY = "Y_HIGH_ONLY"
STATE_BOTH_HIGH_SOLAR_OFF = "BOTH_HIGH_SOLAR_OFF"

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


def read_ems_float(client: ModbusTcpClient, address: int, unit_id: int, byte_order: str) -> float:
    rr = read_holding_registers(client, address, 2, unit_id)
    if _is_modbus_error(rr):
        raise RuntimeError(f"Modbus read failed addr={address} response={rr}")
    return decode_float32(list(rr.registers), byte_order)


def write_ems_float(client: ModbusTcpClient, address: int, value: float, unit_id: int, byte_order: str, readback: bool = True) -> dict[str, Any]:
    regs = encode_float32(value, byte_order)
    rr = write_registers(client, address, regs, unit_id)
    if _is_modbus_error(rr):
        raise RuntimeError(f"Modbus write failed addr={address} value={value} response={rr}")
    out: dict[str, Any] = {"address": address, "value": float(value), "raw_registers": regs}
    if readback:
        out["readback"] = read_ems_float(client, address, unit_id, byte_order)
    return out


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
    if ModbusSerialClient is None:
        raise RuntimeError("pymodbus ModbusSerialClient is not available")
    try:
        client = ModbusSerialClient(
            port=cfg.serial_port,
            baudrate=cfg.baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=cfg.timeout,
        )
    except TypeError:
        client = ModbusSerialClient(  # type: ignore[misc]
            method="rtu",
            port=cfg.serial_port,
            baudrate=cfg.baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=cfg.timeout,
        )
    if not client.connect():
        raise RuntimeError(f"Could not connect to Solis RTU on {cfg.serial_port}")
    return client


def load_controller_state(path: str, *, clear: bool = False) -> dict[str, Any]:
    if clear:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:
            pass
        return {"state": STATE_NORMAL, "solar_off_reason": None, "soc_history": []}
    try:
        data = json.loads(Path(path).read_text())
        if not isinstance(data, dict):
            raise ValueError("state file is not a JSON object")
        data.setdefault("state", STATE_NORMAL)
        data.setdefault("solar_off_reason", None)
        data.setdefault("soc_history", [])
        return data
    except FileNotFoundError:
        return {"state": STATE_NORMAL, "solar_off_reason": None, "soc_history": []}
    except Exception as exc:
        return {"state": STATE_NORMAL, "solar_off_reason": None, "soc_history": [], "state_load_error": str(exc)}


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
    *,
    controller_state: str,
    avg_soc_delta: float | None,
    trend_negative_delta: float,
) -> tuple[str, dict[str, str], str, str, str | None, dict[str, Any]]:
    """Return decision, BESS states, solar state, next state, solar-off reason and details."""
    x_high = soc_x >= high_limit
    y_high = soc_y >= high_limit
    any_at_or_below_recovery = min(soc_x, soc_y) <= recovery_limit
    soc_decreasing = avg_soc_delta is not None and avg_soc_delta < -abs(float(trend_negative_delta))
    recovery_info = {
        "state_before": controller_state,
        "x_high": x_high,
        "y_high": y_high,
        "any_at_or_below_recovery": any_at_or_below_recovery,
        "avg_soc_delta": avg_soc_delta,
        "trend_negative_delta": float(trend_negative_delta),
        "soc_decreasing": soc_decreasing,
    }

    if controller_state == STATE_BOTH_HIGH_SOLAR_OFF:
        if any_at_or_below_recovery and soc_decreasing:
            return "post_both_high_recovered_solar_on_both_bess_on", {"X": "ON", "Y": "ON"}, "ON", STATE_NORMAL, None, recovery_info
        return "both_high_solar_off_waiting_for_recovery", {"X": "ON", "Y": "ON"}, "OFF", STATE_BOTH_HIGH_SOLAR_OFF, "BOTH_BESS_HIGH", recovery_info

    if x_high and y_high:
        return "both_high_keep_both_on_solar_off", {"X": "ON", "Y": "ON"}, "OFF", STATE_BOTH_HIGH_SOLAR_OFF, "BOTH_BESS_HIGH", recovery_info
    if x_high and not y_high:
        return "only_x_high_x_off_y_on_solar_on", {"X": "OFF", "Y": "ON"}, "ON", STATE_X_HIGH_ONLY, None, recovery_info
    if y_high and not x_high:
        return "only_y_high_x_on_y_off_solar_on", {"X": "ON", "Y": "OFF"}, "ON", STATE_Y_HIGH_ONLY, None, recovery_info
    return "normal_keep_both_on_solar_on", {"X": "ON", "Y": "ON"}, "ON", STATE_NORMAL, None, recovery_info


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


def read_solis_status(client: Any, cfg: SolisConfig) -> dict[str, Any]:
    if not cfg.enabled:
        return {"enabled": False}
    if not cfg.status_read_enabled:
        return {"enabled": True, "status_read_enabled": False}
    out: dict[str, Any] = {"enabled": True, "transport": cfg.transport, "serial_port": cfg.serial_port, "unit_id": cfg.unit_id}
    # Best effort only. Some Solis models reject some registers.
    probes = [
        ("operation_status_raw", 3000 - 1, "input"),
        ("active_power_raw", 3005 - 1, "input"),
        ("power_limit_actual_raw", 3052 - 1, "holding"),
    ]
    for name, address, kind in probes:
        try:
            rr = read_input_registers(client, address, 1, cfg.unit_id) if kind == "input" else read_holding_registers(client, address, 1, cfg.unit_id)
            if _is_modbus_error(rr):
                out[name] = {"quality": "bad", "error": str(rr)}
            else:
                out[name] = {"quality": "good", "address": address, "raw": list(rr.registers)}
        except Exception as exc:
            out[name] = {"quality": "bad", "error": str(exc)}
    return out


def command_solis(client: Any, cfg: SolisConfig, target: str, *, live: bool) -> dict[str, Any]:
    if not cfg.enabled:
        return {"device": "Solis", "enabled": False, "target": target, "skipped": True}
    if target not in {"ON", "OFF"}:
        raise ValueError(f"Invalid Solis target={target}")
    if not live:
        return {"device": "Solis", "target": target, "dry_run": True, "method": cfg.control_method, "writes": []}

    writes = []
    if cfg.control_method == "holding_onoff_3007":
        value = SOLIS_HOLDING_ON_VALUE if target == "ON" else SOLIS_HOLDING_OFF_VALUE
        rr = write_register(client, SOLIS_HOLDING_ON_OFF_REGISTER_3007_SEND_ADDRESS, value, cfg.unit_id)
        if _is_modbus_error(rr):
            raise RuntimeError(f"Solis holding ON/OFF write failed addr={SOLIS_HOLDING_ON_OFF_REGISTER_3007_SEND_ADDRESS} value=0x{value:04X} response={rr}")
        writes.append({
            "signal": "solis_on_off_holding_3007",
            "document_register": 3007,
            "send_address": SOLIS_HOLDING_ON_OFF_REGISTER_3007_SEND_ADDRESS,
            "value_hex": f"0x{value:04X}",
            "target": target,
        })
    elif cfg.control_method == "coil_5000":
        value = target == "ON"
        rr = write_coil(client, SOLIS_COIL_GRID_ON_OFF_5000, value, cfg.unit_id)
        if _is_modbus_error(rr):
            raise RuntimeError(f"Solis coil ON/OFF write failed coil={SOLIS_COIL_GRID_ON_OFF_5000} value={value} response={rr}")
        writes.append({"signal": "solis_grid_on_off_coil_5000", "coil": SOLIS_COIL_GRID_ON_OFF_5000, "value": value, "target": target})
    elif cfg.control_method == "power_limit_3052":
        if target == "ON":
            switch_value, limit_value = 0, 10000
        else:
            switch_value, limit_value = 1, 0
        for address, value, signal in [
            (SOLIS_POWER_LIMIT_SWITCH_3070_SEND_ADDRESS, switch_value, "solis_power_limit_switch_3070"),
            (SOLIS_POWER_LIMIT_VALUE_3052_SEND_ADDRESS, limit_value, "solis_power_limit_value_3052"),
        ]:
            rr = write_register(client, address, value, cfg.unit_id)
            if _is_modbus_error(rr):
                raise RuntimeError(f"Solis power-limit write failed addr={address} value={value} response={rr}")
            writes.append({"signal": signal, "send_address": address, "value": value, "target": target})
    else:
        raise ValueError(f"Unsupported Solis control_method={cfg.control_method}")
    return {"device": "Solis", "target": target, "dry_run": False, "method": cfg.control_method, "writes": writes}


def build_action_plan(previous_state: str, desired_bess: dict[str, str], desired_solar: str, solar_enabled: bool) -> list[tuple[str, str, str]]:
    """Build ordered action plan: (kind, key, target).

    v1.8 critical sequence:
    - If previous state was X_HIGH_ONLY/Y_HIGH_ONLY and next target is both-high solar-off,
      switch Solis OFF first, then bring the previously OFF BESS back ON.
    """
    plan: list[tuple[str, str, str]] = []
    both_bess_on = desired_bess.get("X") == "ON" and desired_bess.get("Y") == "ON"
    both_high_target = desired_solar == "OFF" and both_bess_on

    if both_high_target:
        if solar_enabled:
            plan.append(("solar", "Solis", "OFF"))
        if previous_state == STATE_X_HIGH_ONLY:
            # X was previously OFF; bring it back first. Y should already be ON, then re-assert if needed.
            plan.append(("bess", "X", "ON"))
            plan.append(("bess", "Y", "ON"))
        elif previous_state == STATE_Y_HIGH_ONLY:
            plan.append(("bess", "Y", "ON"))
            plan.append(("bess", "X", "ON"))
        else:
            plan.append(("bess", "X", "ON"))
            plan.append(("bess", "Y", "ON"))
        return plan

    # For all other transitions, turn BESS into safe desired states first; if solar is ON, enable it after BESS is ready.
    for key in ("X", "Y"):
        if key in desired_bess:
            plan.append(("bess", key, desired_bess[key]))
    if solar_enabled:
        plan.append(("solar", "Solis", desired_solar))
    return plan


def config_to_arg_defaults(path: str | None) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "x_host": "192.168.100.151",
        "y_host": "192.168.100.153",
        "port": 502,
        "unit_id": 1,
        "byte_order": "ABCD",
        "high_limit": 98.0,
        "recovery_limit": 75.0,
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
        "solis_serial_port": "/dev/ttyUSB1",
        "solis_baudrate": 9600,
        "solis_unit_id": 1,
        "solis_timeout": 3.0,
        "solis_control_method": "holding_onoff_3007",
        "no_solis_status_read": False,
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
    defaults["no_solis_status_read"] = not bool(solis.get("status_read_enabled", not defaults["no_solis_status_read"]))

    soc_logic = data.get("soc_logic", {})
    defaults["high_limit"] = float(soc_logic.get("high_limit", defaults["high_limit"]))
    defaults["recovery_limit"] = float(soc_logic.get("recovery_limit", defaults["recovery_limit"]))
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
    p.add_argument("--high-limit", type=float, default=d["high_limit"])
    p.add_argument("--recovery-limit", type=float, default=d["recovery_limit"])
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
    p.add_argument("--solis-control-method", choices=["holding_onoff_3007", "coil_5000", "power_limit_3052"], default=d["solis_control_method"])
    p.add_argument("--no-solis-status-read", action="store_true", default=d["no_solis_status_read"])
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
    )
    solis_client = make_solis_client(solis_cfg) if solis_cfg.enabled else None

    print(json.dumps({
        "timestamp_utc": utc_now(),
        "event": "soc_solis_controller_started",
        "version": "v1.8_transition_aware",
        "mode": "LIVE_WRITES_ENABLED" if args.live else "DRY_RUN_NO_WRITES",
        "high_limit": args.high_limit,
        "recovery_limit": args.recovery_limit,
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
        },
        "optional_reset_before_on": args.enable_reset_before_on,
        "optional_offgrid_before_on": args.enable_offgrid_before_on,
    }, indent=2))

    try:
        while not _stop:
            cycle: dict[str, Any] = {"timestamp_utc": utc_now(), "live": bool(args.live), "devices": {}, "actions": []}
            try:
                for key, rt in devices.items():
                    rt.soc = read_ems_float(rt.client, REG_SOC, rt.device.unit_id, args.byte_order)
                    rt.online = True
                    rt.last_error = None
                    cycle["devices"][key] = {"host": rt.device.host, "soc": rt.soc, "online": True}

                if solis_cfg.enabled and solis_client is not None:
                    cycle["solar_status_before"] = read_solis_status(solis_client, solis_cfg)

                trend = update_soc_history(controller_state_store, devices["X"].soc, devices["Y"].soc, window_sec=args.soc_trend_window_sec)  # type: ignore[arg-type]
                previous_state = str(controller_state_store.get("state", STATE_NORMAL))
                decision, desired_bess, desired_solar, next_state, solar_off_reason, recovery_info = decide_states(
                    float(devices["X"].soc),
                    float(devices["Y"].soc),
                    args.high_limit,
                    args.recovery_limit,
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
                    "state_file": args.state_file,
                    "trend": trend,
                    "recovery_info": recovery_info,
                }
                cycle["desired_states"] = {"bess": desired_bess, "solar": desired_solar}
                cycle["action_plan"] = [{"kind": k, "id": i, "target": t} for k, i, t in plan]

                for idx, (kind, key, target) in enumerate(plan):
                    if kind == "solar":
                        action = command_solis(solis_client, solis_cfg, target, live=args.live)  # type: ignore[arg-type]
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

                controller_state_store["state"] = next_state
                controller_state_store["solar_off_reason"] = solar_off_reason
                controller_state_store["last_decision"] = decision
                controller_state_store["last_update_utc"] = utc_now()
                controller_state_store["last_soc_x"] = devices["X"].soc
                controller_state_store["last_soc_y"] = devices["Y"].soc
                save_controller_state(args.state_file, controller_state_store)

            except Exception as exc:
                cycle["error"] = str(exc)
                print(json.dumps(cycle, indent=2), flush=True)
                if args.once:
                    return 2
            else:
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
        print(json.dumps({"timestamp_utc": utc_now(), "event": "soc_solis_controller_stopped"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
