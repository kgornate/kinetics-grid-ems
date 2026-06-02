"""
BMS / BCU Modbus TCP Driver - Kinetics Grid EMS Gateway

Purpose:
- Production reusable driver for the BMS/BCU asset.
- Used by bms_gateway_service.py.
- Reads Phase-1 BMS telemetry/status/alarm registers from a Modbus TCP BCU/ModSim server.
- Writes Phase-1 BMS control commands.

Architecture rule:
- This driver does NOT duplicate register addresses, scaling, bitfields, or control values.
- All protocol definitions come from drivers/bms_register_map.py.

Expected network during simulation:
- PC / ModSim IP: 192.168.10.1
- i.MX93 IP: 192.168.10.2
- Modbus TCP port: 502 or 1502
- Unit ID: 1
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

try:
    # pymodbus 3.x
    from pymodbus.client import ModbusTcpClient
except ImportError:  # pragma: no cover - fallback for older environments
    try:
        # pymodbus 2.x
        from pymodbus.client.sync import ModbusTcpClient
    except ImportError:  # pragma: no cover
        ModbusTcpClient = None  # type: ignore

try:
    # Normal package import when running from imx93_gateway root.
    from drivers.bms_register_map import (
        BMS_ASSET_ID,
        BMS_DEFAULT_HOST,
        BMS_DEFAULT_PORT,
        BMS_DEFAULT_UNIT_ID,
        READ_BLOCKS,
        CONTROL_REGISTERS,
        CONTROL_VALUES,
        decode_block,
        build_core_telemetry,
        collect_active_alarms,
    )
except ImportError:  # pragma: no cover - allows standalone testing from drivers folder
    from bms_register_map import (  # type: ignore
        BMS_ASSET_ID,
        BMS_DEFAULT_HOST,
        BMS_DEFAULT_PORT,
        BMS_DEFAULT_UNIT_ID,
        READ_BLOCKS,
        CONTROL_REGISTERS,
        CONTROL_VALUES,
        decode_block,
        build_core_telemetry,
        collect_active_alarms,
    )


@dataclass
class BmsDriverConfig:
    """Configuration for Modbus TCP communication with BMS/BCU."""

    host: str = BMS_DEFAULT_HOST
    port: int = BMS_DEFAULT_PORT
    unit_id: int = BMS_DEFAULT_UNIT_ID
    timeout: float = 2.0
    address_offset: int = 0
    reconnect_delay_sec: float = 1.0


class BmsModbusTcpDriver:
    """
    Low-level BMS/BCU Modbus TCP driver.

    This class only handles protocol communication and decoding. It does not start
    polling threads, logging, or command routing. Those are handled by
    services/bms_gateway_service.py.
    """

    def __init__(self, config: Optional[BmsDriverConfig] = None):
        if ModbusTcpClient is None:
            raise RuntimeError("pymodbus is not installed. Install with: pip3 install pymodbus")

        self.config = config or BmsDriverConfig()
        self.client = ModbusTcpClient(
            host=self.config.host,
            port=self.config.port,
            timeout=self.config.timeout,
        )
        self.connected: bool = False
        self.last_error: Optional[str] = None
        self.last_success_ts: Optional[float] = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------
    def connect(self) -> bool:
        """Connect to the Modbus TCP server."""
        try:
            self.connected = bool(self.client.connect())
            if self.connected:
                self.last_error = None
                self.last_success_ts = time.time()
            else:
                self.last_error = "Could not connect to BMS Modbus TCP server"
            return self.connected
        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)
            return False

    def close(self) -> None:
        """Close the Modbus TCP connection."""
        try:
            self.client.close()
        except Exception:
            pass
        self.connected = False

    def ensure_connected(self) -> bool:
        """Reconnect if required."""
        if self.connected:
            return True
        return self.connect()

    def _addr(self, address: int) -> int:
        """Apply optional ModSim address offset."""
        return address + self.config.address_offset

    # ------------------------------------------------------------------
    # Raw Modbus helpers with pymodbus 2.x / 3.x compatibility
    # ------------------------------------------------------------------
    def read_holding_registers(self, address: int, count: int) -> List[int]:
        """Read holding registers and return raw register list."""
        if not self.ensure_connected():
            raise RuntimeError(self.last_error or "BMS Modbus TCP not connected")

        actual_address = self._addr(address)
        try:
            try:
                rr = self.client.read_holding_registers(
                    address=actual_address,
                    count=count,
                    device_id=self.config.unit_id,
                )
            except TypeError:
                try:
                    rr = self.client.read_holding_registers(
                        address=actual_address,
                        count=count,
                        slave=self.config.unit_id,
                    )
                except TypeError:
                    rr = self.client.read_holding_registers(
                        address=actual_address,
                        count=count,
                        unit=self.config.unit_id,
                    )

            if rr is None:
                self.connected = False
                raise RuntimeError("No response from BMS Modbus TCP server")
            if hasattr(rr, "isError") and rr.isError():
                raise RuntimeError(f"Modbus read error at 0x{address:04X}: {rr}")
            if not hasattr(rr, "registers"):
                raise RuntimeError(f"Invalid Modbus read response at 0x{address:04X}: {rr}")

            self.last_error = None
            self.last_success_ts = time.time()
            return list(rr.registers)
        except Exception as exc:
            self.last_error = str(exc)
            # Most Modbus exceptions mean connection may be unhealthy.
            self.connected = False
            raise

    def write_register(self, address: int, value: int) -> None:
        """Write one holding register."""
        if not self.ensure_connected():
            raise RuntimeError(self.last_error or "BMS Modbus TCP not connected")

        actual_address = self._addr(address)
        value = int(value) & 0xFFFF

        try:
            try:
                wr = self.client.write_register(
                    address=actual_address,
                    value=value,
                    device_id=self.config.unit_id,
                )
            except TypeError:
                try:
                    wr = self.client.write_register(
                        address=actual_address,
                        value=value,
                        slave=self.config.unit_id,
                    )
                except TypeError:
                    wr = self.client.write_register(
                        address=actual_address,
                        value=value,
                        unit=self.config.unit_id,
                    )

            if wr is None:
                self.connected = False
                raise RuntimeError("No response from BMS Modbus TCP server")
            if hasattr(wr, "isError") and wr.isError():
                raise RuntimeError(f"Modbus write error at 0x{address:04X}: {wr}")

            self.last_error = None
            self.last_success_ts = time.time()
        except Exception as exc:
            self.last_error = str(exc)
            self.connected = False
            raise

    # ------------------------------------------------------------------
    # Decoded read APIs
    # ------------------------------------------------------------------
    def read_measurements(self) -> Dict[str, Any]:
        """Read and decode Rack Measure Phase-1 block."""
        block = READ_BLOCKS["rack_measure_phase1"]
        raw = self.read_holding_registers(block["start"], block["count"])
        return decode_block(raw, "rack_measure_phase1")

    def read_status(self) -> Dict[str, Any]:
        """Read and decode Rack Signal Phase-1 block.

        This includes both alarm bitfields and system status registers.
        """
        block = READ_BLOCKS["rack_signal_phase1"]
        raw = self.read_holding_registers(block["start"], block["count"])
        return decode_block(raw, "rack_signal_phase1")

    def read_alarms(self) -> Dict[str, Any]:
        """Read BMS status block and return flattened active alarms."""
        status = self.read_status()
        active = collect_active_alarms(status)
        return {
            "active_alarms": active,
            "alarm_count": len(active),
            "decoded_status_block": status,
        }

    def read_all(self) -> Dict[str, Any]:
        """Read measurements + status/alarm blocks and return EMS-friendly payload."""
        measurements = self.read_measurements()
        status = self.read_status()
        core = build_core_telemetry(measurements, status)
        active_alarms = collect_active_alarms(status)

        core.update(
            {
                "asset_id": BMS_ASSET_ID,
                "communication_status": "online",
                "active_alarms": active_alarms,
                "alarm_count": len(active_alarms),
                "last_error": None,
            }
        )
        return core

    def get_comm_status(self) -> Dict[str, Any]:
        """Return current communication metadata."""
        return {
            "connected": self.connected,
            "last_error": self.last_error,
            "last_success_ts": self.last_success_ts,
            "host": self.config.host,
            "port": self.config.port,
            "unit_id": self.config.unit_id,
        }

    # ------------------------------------------------------------------
    # Control command APIs
    # ------------------------------------------------------------------
    def _write_control(self, control_key: str, value_key: str) -> Dict[str, Any]:
        if control_key not in CONTROL_REGISTERS:
            raise KeyError(f"Unknown BMS control register: {control_key}")
        if control_key not in CONTROL_VALUES:
            raise KeyError(f"No control values defined for: {control_key}")
        if value_key not in CONTROL_VALUES[control_key]:
            raise KeyError(f"Unknown control value '{value_key}' for {control_key}")

        reg = CONTROL_REGISTERS[control_key]
        value = CONTROL_VALUES[control_key][value_key]
        self.write_register(reg.address, value)
        return {
            "status": "ok",
            "asset_id": BMS_ASSET_ID,
            "control_key": control_key,
            "command": value_key,
            "address": f"0x{reg.address:04X}",
            "value": value,
            "message": f"{reg.name} command '{value_key}' written successfully",
        }

    def start_insulation_sampling(self) -> Dict[str, Any]:
        return self._write_control("start_insulation_sampling", "start")

    def start_precharge(self) -> Dict[str, Any]:
        return self._write_control("start_precharge", "start")

    def stop_precharge(self) -> Dict[str, Any]:
        return self._write_control("start_precharge", "stop")

    def reset_bcu(self) -> Dict[str, Any]:
        return self._write_control("bcu_reset", "reset")

    def fan_auto(self) -> Dict[str, Any]:
        return self._write_control("fan_switch", "auto")

    def fan_on(self) -> Dict[str, Any]:
        return self._write_control("fan_switch", "on")

    def fan_off(self) -> Dict[str, Any]:
        return self._write_control("fan_switch", "off")

    def execute_command(self, command: str) -> Dict[str, Any]:
        """Generic command dispatcher used by gateway service/TCP command server."""
        command = command.strip().upper()
        command_map = {
            "START_BMS_INSULATION_TEST": self.start_insulation_sampling,
            "START_INSULATION_TEST": self.start_insulation_sampling,
            "START_INSULATION": self.start_insulation_sampling,
            "START_BMS_PRECHARGE": self.start_precharge,
            "START_PRECHARGE": self.start_precharge,
            "STOP_BMS_PRECHARGE": self.stop_precharge,
            "STOP_PRECHARGE": self.stop_precharge,
            "RESET_BCU": self.reset_bcu,
            "BMS_FAN_AUTO": self.fan_auto,
            "FAN_AUTO": self.fan_auto,
            "BMS_FAN_ON": self.fan_on,
            "FAN_ON": self.fan_on,
            "BMS_FAN_OFF": self.fan_off,
            "FAN_OFF": self.fan_off,
        }
        if command not in command_map:
            return {
                "status": "error",
                "asset_id": BMS_ASSET_ID,
                "command": command,
                "message": f"Unsupported BMS command: {command}",
            }
        try:
            result = command_map[command]()
            result["command"] = command
            return result
        except Exception as exc:
            return {
                "status": "error",
                "asset_id": BMS_ASSET_ID,
                "command": command,
                "message": str(exc),
            }


# -----------------------------------------------------------------------------
# Minimal standalone smoke test
# -----------------------------------------------------------------------------
def _main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Standalone BMS Modbus TCP driver smoke test")
    parser.add_argument("--host", default=BMS_DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=BMS_DEFAULT_PORT)
    parser.add_argument("--unit-id", type=int, default=BMS_DEFAULT_UNIT_ID)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--address-offset", type=int, default=0)
    parser.add_argument("--read-all", action="store_true")
    parser.add_argument("--read-alarms", action="store_true")
    parser.add_argument("--fan-on", action="store_true")
    parser.add_argument("--fan-off", action="store_true")
    parser.add_argument("--fan-auto", action="store_true")
    parser.add_argument("--start-precharge", action="store_true")
    parser.add_argument("--stop-precharge", action="store_true")
    parser.add_argument("--start-insulation", action="store_true")
    parser.add_argument("--reset-bcu", action="store_true")
    args = parser.parse_args()

    driver = BmsModbusTcpDriver(
        BmsDriverConfig(
            host=args.host,
            port=args.port,
            unit_id=args.unit_id,
            timeout=args.timeout,
            address_offset=args.address_offset,
        )
    )

    try:
        if not driver.connect():
            print(json.dumps(driver.get_comm_status(), indent=2))
            return 2

        if args.fan_on:
            result = driver.fan_on()
        elif args.fan_off:
            result = driver.fan_off()
        elif args.fan_auto:
            result = driver.fan_auto()
        elif args.start_precharge:
            result = driver.start_precharge()
        elif args.stop_precharge:
            result = driver.stop_precharge()
        elif args.start_insulation:
            result = driver.start_insulation_sampling()
        elif args.reset_bcu:
            result = driver.reset_bcu()
        elif args.read_alarms:
            result = driver.read_alarms()
        else:
            result = driver.read_all()

        print(json.dumps(result, indent=2, default=str))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(_main())
