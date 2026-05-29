#!/usr/bin/env python3
"""
PCS TCP CLI

Purpose:
- Direct testing tool for PCS/Inverter Modbus TCP communication.
- Supports vendor profiles:
    - njoy / enjoy 125kW PCS
    - inpower / empower 125kW PCS

Use this before or alongside EMS gateway integration.

Examples:

Njoy read:
python3 pcs_tcp_cli.py --vendor njoy --host 192.168.10.1 --port 502 --unit 1 read

Inpower read:
python3 pcs_tcp_cli.py --vendor inpower --host 192.168.10.1 --port 502 --unit 1 read

Inpower active power:
python3 pcs_tcp_cli.py --vendor inpower --host 192.168.10.1 --port 502 --unit 1 set-active-power --kw 20

For Inpower:
+20 kW EMS discharge/export will write raw -200 to holding register 304.
"""

import argparse
import json
import sys
from typing import Any

from drivers.pcs_modbus_tcp_driver import PcsModbusTcpDriver
from drivers.pcs_profiles import njoy_125kw_profile as njoy
from drivers.pcs_profiles import inpower_125kw_profile as inpower


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2))


def get_profile(vendor: str):
    vendor_l = vendor.lower()

    if vendor_l in ("njoy", "enjoy", "njoy_125kw", "enjoy_125kw"):
        return njoy

    if vendor_l in ("inpower", "empower", "inpower_125kw", "empower_125kw"):
        return inpower

    raise ValueError(f"Unsupported vendor: {vendor}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PCS/Inverter Modbus TCP CLI for i.MX93 EMS Gateway"
    )

    parser.add_argument(
        "--vendor",
        default="njoy",
        choices=["njoy", "enjoy", "inpower", "empower"],
        help="PCS vendor profile to use.",
    )

    parser.add_argument(
        "--host",
        default="192.168.10.1",
        help="PCS / ModSim IP address. Current lab default: 192.168.10.1",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=502,
        help="PCS / ModSim TCP port. Default: 502",
    )

    parser.add_argument(
        "--unit",
        type=int,
        default=1,
        help="Modbus unit/slave ID. Default: 1",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="TCP timeout in seconds. Default: 3.0",
    )

    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Number of retry attempts. Default: 2",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("read", help="Read PCS telemetry using selected vendor profile")

    subparsers.add_parser("power-on", help="Send PCS power ON/start command")

    subparsers.add_parser("power-off", help="Send PCS power OFF/shutdown command")

    subparsers.add_parser("standby", help="Send PCS standby command if supported")

    p_active = subparsers.add_parser("set-active-power", help="Set active power in kW")
    p_active.add_argument(
        "--kw",
        type=float,
        required=True,
        help="Active power in kW. EMS convention: positive = discharge/export, negative = charge/import.",
    )

    p_reactive = subparsers.add_parser("set-reactive-power", help="Set reactive power in kvar")
    p_reactive.add_argument(
        "--kvar",
        type=float,
        required=True,
        help="Reactive power in kvar.",
    )

    subparsers.add_parser("reset-fault", help="Send PCS fault reset command")

    p_heartbeat = subparsers.add_parser("heartbeat", help="Write heartbeat value if supported")
    p_heartbeat.add_argument(
        "--value",
        type=int,
        required=True,
        help="Heartbeat value 0-255.",
    )

    p_raw_read = subparsers.add_parser("raw-read", help="Raw Modbus read")
    p_raw_read.add_argument(
        "--type",
        choices=["holding", "input", "coil", "discrete"],
        default="holding",
        help="Modbus area to read. Default: holding",
    )
    p_raw_read.add_argument(
        "--address",
        required=True,
        help="Register/coil address. Supports decimal or hex, e.g. 304 or 0x0130.",
    )
    p_raw_read.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of registers/coils to read.",
    )

    p_raw_write = subparsers.add_parser("raw-write", help="Raw Modbus write")
    p_raw_write.add_argument(
        "--type",
        choices=["holding", "coil"],
        default="holding",
        help="Modbus area to write. Default: holding",
    )
    p_raw_write.add_argument(
        "--address",
        required=True,
        help="Register/coil address. Supports decimal or hex.",
    )
    p_raw_write.add_argument(
        "--value",
        required=True,
        help="Value to write. For coil use 1/0 or true/false.",
    )

    return parser


def parse_int(value: str) -> int:
    return int(value, 0)


def parse_bool(value: str) -> bool:
    v = str(value).strip().lower()

    if v in ("1", "true", "on", "yes", "y"):
        return True

    if v in ("0", "false", "off", "no", "n"):
        return False

    raise ValueError(f"Invalid boolean value: {value}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    profile = get_profile(args.vendor)

    driver = PcsModbusTcpDriver(
        host=args.host,
        port=args.port,
        unit_id=args.unit,
        timeout=args.timeout,
        retries=args.retries,
    )

    print(
        f"[INFO] Connecting to PCS/Simulator: "
        f"{args.host}:{args.port}, unit={args.unit}, vendor={args.vendor}"
    )

    if not driver.connect():
        print("[ERROR] Failed to connect to PCS/Simulator")
        return 1

    print("[OK] Connected")

    try:
        if args.command == "read":
            telemetry = profile.read_telemetry(driver)
            print_json(telemetry)

        elif args.command == "power-on":
            profile.power_on(driver)
            print("[OK] Power ON / Startup command written")

        elif args.command == "power-off":
            profile.power_off(driver)
            print("[OK] Power OFF / Shutdown command written")

        elif args.command == "standby":
            if not hasattr(profile, "standby"):
                print(f"[ERROR] Standby command not supported for vendor: {args.vendor}")
                return 2

            profile.standby(driver)
            print("[OK] Standby command written")

        elif args.command == "set-active-power":
            profile.set_active_power_kw(driver, args.kw)
            raw = profile.kw_to_raw(args.kw)
            print(f"[OK] Active power setpoint written: {args.kw} kW, raw={raw}")

        elif args.command == "set-reactive-power":
            profile.set_reactive_power_kvar(driver, args.kvar)
            raw = profile.kvar_to_raw(args.kvar)
            print(f"[OK] Reactive power setpoint written: {args.kvar} kvar, raw={raw}")

        elif args.command == "reset-fault":
            profile.reset_fault(driver)
            print("[OK] Fault reset command written")

        elif args.command == "heartbeat":
            if getattr(profile, "HEARTBEAT_SUPPORTED", True) is False:
                print(f"[ERROR] Heartbeat not supported for vendor: {args.vendor}")
                return 2

            profile.write_heartbeat(driver, args.value)
            print(f"[OK] Heartbeat written: {args.value % 256}")

        elif args.command == "raw-read":
            address = parse_int(args.address)

            if args.type == "holding":
                values = driver.read_holding_registers(address, args.count)
                print_json(
                    {
                        "type": args.type,
                        "address_dec": address,
                        "address_hex": hex(address),
                        "count": args.count,
                        "values": values,
                        "values_hex": [hex(v) for v in values],
                        "values_s16": [PcsModbusTcpDriver.to_s16(v) for v in values],
                    }
                )

            elif args.type == "input":
                values = driver.read_input_registers(address, args.count)
                print_json(
                    {
                        "type": args.type,
                        "address_dec": address,
                        "address_hex": hex(address),
                        "count": args.count,
                        "values": values,
                        "values_hex": [hex(v) for v in values],
                        "values_s16": [PcsModbusTcpDriver.to_s16(v) for v in values],
                    }
                )

            elif args.type == "coil":
                values = driver.read_coils(address, args.count)
                print_json(
                    {
                        "type": args.type,
                        "address_dec": address,
                        "address_hex": hex(address),
                        "count": args.count,
                        "values": values,
                    }
                )

            elif args.type == "discrete":
                values = driver.read_discrete_inputs(address, args.count)
                print_json(
                    {
                        "type": args.type,
                        "address_dec": address,
                        "address_hex": hex(address),
                        "count": args.count,
                        "values": values,
                    }
                )

        elif args.command == "raw-write":
            address = parse_int(args.address)

            if args.type == "holding":
                value = parse_int(args.value)
                driver.write_register(address, value)

                print(
                    f"[OK] Raw holding write successful: "
                    f"address={address} ({hex(address)}), "
                    f"value={value} ({hex(PcsModbusTcpDriver.to_u16(value))})"
                )

            elif args.type == "coil":
                value = parse_bool(args.value)
                driver.write_coil(address, value)

                print(
                    f"[OK] Raw coil write successful: "
                    f"address={address} ({hex(address)}), "
                    f"value={value}"
                )

        else:
            print(f"[ERROR] Unknown command: {args.command}")
            return 1

    except Exception as exc:
        print(f"[ERROR] Command failed: {exc}")
        return 2

    finally:
        driver.close()
        print("[INFO] Connection closed")

    return 0


if __name__ == "__main__":
    sys.exit(main())