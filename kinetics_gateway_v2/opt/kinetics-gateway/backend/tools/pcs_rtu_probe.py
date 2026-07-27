#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.protocols.modbus_rtu import ModbusRtuClient


def parse_int(value: str) -> int:
    return int(value, 0)


def parse_unit_ids(value: str) -> list[int]:
    result = [parse_int(item.strip()) for item in value.split(",") if item.strip()]
    if not result:
        raise argparse.ArgumentTypeError("At least one unit ID is required")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only Modbus RTU probe for the four Kinetics PCS slaves"
    )
    parser.add_argument("--device", default="/dev/pcs_rs485")
    parser.add_argument("--baudrate", type=int, required=True)
    parser.add_argument("--bytesize", type=int, choices=(7, 8), default=8)
    parser.add_argument("--parity", choices=("N", "E", "O"), default="N")
    parser.add_argument("--stopbits", type=int, choices=(1, 2), default=1)
    parser.add_argument("--unit-ids", type=parse_unit_ids, required=True)
    parser.add_argument("--address", type=parse_int, default=0x0001)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--function", type=int, choices=(3, 4), default=3)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--delay-ms", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = ModbusRtuClient(
        device=args.device,
        baudrate=args.baudrate,
        bytesize=args.bytesize,
        parity=args.parity,
        stopbits=args.stopbits,
        timeout=args.timeout,
        inter_request_delay_ms=args.delay_ms,
        retries=args.retries,
    )
    successes = 0
    try:
        for unit_id in args.unit_ids:
            result = {
                "device": args.device,
                "baudrate": args.baudrate,
                "parity": args.parity,
                "stopbits": args.stopbits,
                "unit_id": unit_id,
                "function_code": args.function,
                "address": args.address,
                "count": args.count,
            }
            try:
                result["registers"] = client.read_registers(
                    unit_id, args.address, args.count, args.function
                )
                result["ok"] = True
                successes += 1
            except Exception as error:
                result["ok"] = False
                result["error"] = str(error)
            print(json.dumps(result, ensure_ascii=False))
    finally:
        client.close()
    print(json.dumps({"summary": {"attempts": len(args.unit_ids), "successes": successes}}))
    return 0 if successes == len(args.unit_ids) else 2


if __name__ == "__main__":
    raise SystemExit(main())
