#!/usr/bin/env python3
"""
BMS / BCU Modbus TCP CLI Test Tool for Kinetics Grid EMS

Purpose:
- Run this on i.MX93 to test BMS register reads/writes against PC ModSim.
- Uses drivers/bms_register_map.py as the single source of truth for:
  register addresses, read blocks, scaling, bitfield decoding, status decoding,
  and control command values.

Default network setup:
- PC / ModSim IP: 192.168.10.1
- i.MX93 IP:     192.168.10.2

Example usage:
    python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --read-core
    python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --read-alarms
    python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --read-status
    python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --read-all
    python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --start-precharge
    python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --stop-precharge
    python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --start-insulation
    python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --fan-auto
    python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --fan-on
    python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --fan-off
    python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --reset-bcu

Address convention:
- This CLI uses zero-based Modbus protocol addresses by default.
- Excel address 0x0210 = decimal 528.
- If ModSim display uses 40001-style display addressing, configure ModSim carefully.
- If your simulator behaves as 1-based, use --address-offset 1 or -1 only after testing.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

# Allow running from imx93_gateway root even if this file is in tools/.
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

try:
    # Preferred location inside gateway source tree.
    from drivers.bms_register_map import (
        BMS_DEFAULT_HOST,
        BMS_DEFAULT_PORT,
        BMS_DEFAULT_UNIT_ID,
        READ_BLOCKS,
        CONTROL_REGISTERS,
        CONTROL_VALUES,
        RACK_SIGNAL_REGISTERS,
        decode_block,
        build_core_telemetry,
        collect_active_alarms,
    )
except ImportError as exc:
    raise SystemExit(
        "ERROR: Could not import drivers.bms_register_map.\n"
        "Place bms_register_map.py at: imx93_gateway/drivers/bms_register_map.py\n"
        f"Import error: {exc}"
    )

try:
    # pymodbus 3.x
    from pymodbus.client import ModbusTcpClient
except ImportError:
    try:
        # pymodbus 2.x fallback
        from pymodbus.client.sync import ModbusTcpClient
    except ImportError:
        ModbusTcpClient = None  # type: ignore


@dataclass
class CliConfig:
    host: str
    port: int
    unit_id: int
    timeout: float
    address_offset: int


def print_section(title: str) -> None:
    print("\n" + "=" * 76)
    print(title)
    print("=" * 76)


def format_value(value: Any, unit: str = "") -> str:
    if value is None:
        text = "N/A"
    elif isinstance(value, float):
        text = f"{value:.2f}" if math.isfinite(value) else str(value)
    elif isinstance(value, list):
        text = ", ".join(str(v) for v in value) if value else "None"
    else:
        text = str(value)
    return f"{text} {unit}".strip() if unit else text


def print_kv(key: str, value: Any, unit: str = "") -> None:
    print(f"{key:<42}: {format_value(value, unit)}")


class BmsCliClient:
    def __init__(self, config: CliConfig):
        if ModbusTcpClient is None:
            raise RuntimeError("pymodbus is not installed. Install with: pip3 install pymodbus")
        self.config = config
        self.client = ModbusTcpClient(host=config.host, port=config.port, timeout=config.timeout)

    def connect(self) -> bool:
        return bool(self.client.connect())

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass

    def _addr(self, address: int) -> int:
        return address + self.config.address_offset

    def read_holding_registers(self, address: int, count: int) -> List[int]:
        request_address = self._addr(address)
        try:
            rr = self.client.read_holding_registers(
                address=request_address,
                count=count,
                device_id=self.config.unit_id,
            )
        except TypeError:
            try:
                rr = self.client.read_holding_registers(
                    address=request_address,
                    count=count,
                    slave=self.config.unit_id,
                )
            except TypeError:
                rr = self.client.read_holding_registers(
                    address=request_address,
                    count=count,
                    unit=self.config.unit_id,
                )

        if rr is None:
            raise RuntimeError(f"No response from Modbus server for address 0x{address:04X}")
        if hasattr(rr, "isError") and rr.isError():
            raise RuntimeError(f"Modbus error response for address 0x{address:04X}: {rr}")
        if not hasattr(rr, "registers"):
            raise RuntimeError(f"Invalid Modbus response for address 0x{address:04X}: {rr}")
        return list(rr.registers)

    def write_register(self, address: int, value: int) -> None:
        request_address = self._addr(address)
        value = int(value) & 0xFFFF
        try:
            wr = self.client.write_register(
                address=request_address,
                value=value,
                device_id=self.config.unit_id,
            )
        except TypeError:
            try:
                wr = self.client.write_register(
                    address=request_address,
                    value=value,
                    slave=self.config.unit_id,
                )
            except TypeError:
                wr = self.client.write_register(
                    address=request_address,
                    value=value,
                    unit=self.config.unit_id,
                )

        if wr is None:
            raise RuntimeError(f"No response from Modbus server for write address 0x{address:04X}")
        if hasattr(wr, "isError") and wr.isError():
            raise RuntimeError(f"Modbus write error response for address 0x{address:04X}: {wr}")

    def read_measurements(self) -> Dict[str, Any]:
        block = READ_BLOCKS["rack_measure_core"]
        regs = self.read_holding_registers(block["start"], block["count"])
        return decode_block(regs, "rack_measure_core")

    def read_status_block(self) -> Dict[str, Any]:
        block = READ_BLOCKS["rack_signal_core"]
        regs = self.read_holding_registers(block["start"], block["count"])
        return decode_block(regs, "rack_signal_core")

    def read_core_payload(self) -> Dict[str, Any]:
        measurements = self.read_measurements()
        status = self.read_status_block()
        payload = build_core_telemetry(measurements, status)
        active_alarms = collect_active_alarms(status)
        payload["active_alarms"] = active_alarms
        payload["alarm_count"] = len(active_alarms)
        payload["communication_status"] = "online"
        return payload

    def write_control(self, control_key: str, value_key: str) -> None:
        if control_key not in CONTROL_REGISTERS:
            raise ValueError(f"Unknown control register key: {control_key}")
        if control_key not in CONTROL_VALUES:
            raise ValueError(f"No CONTROL_VALUES defined for: {control_key}")
        values = CONTROL_VALUES[control_key]
        if value_key not in values:
            raise ValueError(f"Unknown value '{value_key}' for control '{control_key}'")
        self.write_register(CONTROL_REGISTERS[control_key].address, values[value_key])

    def start_insulation_sampling(self) -> None:
        self.write_control("start_insulation_sampling", "start")

    def start_precharge(self) -> None:
        self.write_control("start_precharge", "start")

    def stop_precharge(self) -> None:
        self.write_control("start_precharge", "stop")

    def reset_bcu(self) -> None:
        self.write_control("bcu_reset", "reset")

    def fan_auto(self) -> None:
        self.write_control("fan_switch", "auto")

    def fan_on(self) -> None:
        self.write_control("fan_switch", "on")

    def fan_off(self) -> None:
        self.write_control("fan_switch", "off")


def print_core_payload(payload: Mapping[str, Any]) -> None:
    print_section("BMS / BCU Core Telemetry")
    print_kv("Asset ID", payload.get("asset_id"))
    print_kv("Communication status", payload.get("communication_status"))
    print_kv("SOC", payload.get("soc_percent"), "%")
    print_kv("SOH", payload.get("soh_percent"), "%")
    print_kv("Rack internal SOC", payload.get("rack_inner_soc_percent"), "%")
    print_kv("Rack voltage", payload.get("rack_voltage_v"), "V")
    print_kv("Rack current", payload.get("rack_current_a"), "A")
    print_kv("Calculated power", payload.get("power_kw"), "kW")
    print_kv("Max allowed charge current", payload.get("max_allowed_charge_current_a"), "A")
    print_kv("Max allowed discharge current", payload.get("max_allowed_discharge_current_a"), "A")

    print_section("Cell Voltage Statistics")
    print_kv("Max cell voltage", payload.get("max_cell_voltage_mv"), "mV")
    print_kv("Min cell voltage", payload.get("min_cell_voltage_mv"), "mV")
    print_kv("Average cell voltage", payload.get("avg_cell_voltage_mv"), "mV")
    print_kv("Cell voltage difference", payload.get("cell_voltage_diff_mv"), "mV")

    print_section("Temperature Statistics")
    print_kv("Max cell temperature", payload.get("max_cell_temp_c"), "°C")
    print_kv("Min cell temperature", payload.get("min_cell_temp_c"), "°C")
    print_kv("Average rack temperature", payload.get("avg_temp_c"), "°C")
    print_kv("Max temperature difference", payload.get("max_temp_diff_c"), "°C")

    print_section("Safety and Status")
    print_kv("Insulation resistance", payload.get("insulation_resistance_kohm"), "kΩ")
    print_kv("Positive insulation resistance", payload.get("positive_insulation_resistance_kohm"), "kΩ")
    print_kv("Negative insulation resistance", payload.get("negative_insulation_resistance_kohm"), "kΩ")
    print_kv("Precharge stage", payload.get("precharge_stage"))
    print_kv("BCU state", payload.get("bcu_state"))
    print_kv("Charge/discharge state", payload.get("current_state"))
    print_kv("Heartbeat", payload.get("heartbeat"))
    print_kv("Positive contactor closed", payload.get("positive_contactor_closed"))
    print_kv("Precharge contactor closed", payload.get("precharge_contactor_closed"))
    print_kv("Negative contactor closed", payload.get("negative_contactor_closed"))
    print_kv("Contactor active flags", payload.get("contactor_active_flags"))

    print_section("Alarm Summary")
    print_kv("Alarm count", payload.get("alarm_count"))
    active_alarms = payload.get("active_alarms") or []
    if not active_alarms:
        print("No active alarms.")
    else:
        for alarm in active_alarms:
            print(f"  - {alarm}")


def print_status_block(status: Mapping[str, Any]) -> None:
    print_section("BMS / BCU Status Block")
    for key, entry in status.items():
        reg = RACK_SIGNAL_REGISTERS.get(key)
        name = reg.name if reg else key
        if isinstance(entry, Mapping):
            raw = entry.get("raw")
            decoded = entry.get("decoded")
            active = entry.get("active")
            if decoded is not None:
                print_kv(name, f"raw={raw}, decoded={decoded}")
            elif active is not None:
                active_text = ", ".join(active) if active else "None"
                print_kv(name, f"raw=0x{int(raw or 0):04X}, active={active_text}")
            else:
                print_kv(name, entry)
        else:
            print_kv(name, entry)


def print_alarms(status: Mapping[str, Any]) -> None:
    print_section("BMS / BCU Alarms")
    active_alarms = collect_active_alarms(status)

    print("Non-zero alarm/status bitfield registers:")
    found_non_zero = False
    for key, entry in status.items():
        if not isinstance(entry, Mapping):
            continue
        raw = int(entry.get("raw") or 0)
        active = entry.get("active")
        if active is None or raw == 0:
            continue
        found_non_zero = True
        reg = RACK_SIGNAL_REGISTERS.get(key)
        name = reg.name if reg else key
        active_text = ", ".join(active) if active else "None"
        print(f"  0x{reg.address:04X}  {name:<35} raw=0x{raw:04X}  active={active_text}")

    if not found_non_zero:
        print("  None")

    print("\nActive decoded alarms:")
    if not active_alarms:
        print("  None")
    else:
        for alarm in active_alarms:
            print(f"  - {alarm}")


def print_measurements(measurements: Mapping[str, Any]) -> None:
    print_section("Decoded Rack Measurements")
    for key, value in measurements.items():
        print_kv(key, value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BMS / BCU Modbus TCP CLI for Kinetics Grid EMS")
    parser.add_argument("--host", default=BMS_DEFAULT_HOST, help=f"Modbus TCP server IP address, default {BMS_DEFAULT_HOST}")
    parser.add_argument("--port", type=int, default=BMS_DEFAULT_PORT, help=f"Modbus TCP server port, default {BMS_DEFAULT_PORT}")
    parser.add_argument("--unit-id", type=int, default=BMS_DEFAULT_UNIT_ID, help=f"Modbus unit/slave ID, default {BMS_DEFAULT_UNIT_ID}")
    parser.add_argument("--timeout", type=float, default=2.0, help="Modbus timeout seconds, default 2.0")
    parser.add_argument(
        "--address-offset",
        type=int,
        default=0,
        help="Optional address offset if simulator uses 1-based addressing. Usually keep 0.",
    )

    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--read-core", action="store_true", help="Read EMS-friendly telemetry/status/alarm payload")
    actions.add_argument("--read-measurements", action="store_true", help="Read and print decoded rack measurement block")
    actions.add_argument("--read-status", action="store_true", help="Read and print decoded rack signal/status block")
    actions.add_argument("--read-alarms", action="store_true", help="Read alarm/status bitfields")
    actions.add_argument("--read-all", action="store_true", help="Read core payload, measurements, status and alarms")
    actions.add_argument("--start-insulation", action="store_true", help="Write start insulation sampling command")
    actions.add_argument("--start-precharge", action="store_true", help="Write start precharge command")
    actions.add_argument("--stop-precharge", action="store_true", help="Write stop precharge command")
    actions.add_argument("--reset-bcu", action="store_true", help="Write reset BCU command")
    actions.add_argument("--fan-auto", action="store_true", help="Set fan control to auto/no-force")
    actions.add_argument("--fan-on", action="store_true", help="Force fan ON")
    actions.add_argument("--fan-off", action="store_true", help="Force fan OFF")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = CliConfig(
        host=args.host,
        port=args.port,
        unit_id=args.unit_id,
        timeout=args.timeout,
        address_offset=args.address_offset,
    )

    client = BmsCliClient(config)
    print(f"Connecting to BMS Modbus TCP server {args.host}:{args.port}, unit_id={args.unit_id} ...")

    try:
        if not client.connect():
            print("ERROR: Could not connect to Modbus TCP server.", file=sys.stderr)
            return 2

        if args.read_core:
            print_core_payload(client.read_core_payload())
        elif args.read_measurements:
            print_measurements(client.read_measurements())
        elif args.read_status:
            print_status_block(client.read_status_block())
        elif args.read_alarms:
            print_alarms(client.read_status_block())
        elif args.read_all:
            measurements = client.read_measurements()
            status = client.read_status_block()
            payload = build_core_telemetry(measurements, status)
            active_alarms = collect_active_alarms(status)
            payload["active_alarms"] = active_alarms
            payload["alarm_count"] = len(active_alarms)
            payload["communication_status"] = "online"
            print_core_payload(payload)
            print_measurements(measurements)
            print_status_block(status)
            print_alarms(status)
        elif args.start_insulation:
            client.start_insulation_sampling()
            print("Start insulation sampling command written successfully.")
        elif args.start_precharge:
            client.start_precharge()
            print("Start precharge command written successfully.")
        elif args.stop_precharge:
            client.stop_precharge()
            print("Stop precharge command written successfully.")
        elif args.reset_bcu:
            client.reset_bcu()
            print("Reset BCU command written successfully.")
        elif args.fan_auto:
            client.fan_auto()
            print("Fan control set to AUTO / no force.")
        elif args.fan_on:
            client.fan_on()
            print("Fan control set to FORCE ON.")
        elif args.fan_off:
            client.fan_off()
            print("Fan control set to FORCE OFF.")

        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
