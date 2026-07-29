#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from typing import Any

from app.protocols.modbus_tcp import ModbusTcpClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only Modbus TCP endpoint probe")
    parser.add_argument("--host", required=True)
    parser.add_argument("--ports", type=int, nargs="+", default=[503])
    parser.add_argument("--unit-ids", type=int, nargs="+", default=[1, 2, 3, 4, 5, 127])
    parser.add_argument("--address", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--functions", type=int, nargs="+", default=[3, 4])
    parser.add_argument("--timeout", type=float, default=1.5)
    parser.add_argument("--source-ip", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results: list[dict[str, Any]] = []
    for port in args.ports:
        client = ModbusTcpClient(args.host, port, args.timeout, source_ip=args.source_ip)
        for unit_id in args.unit_ids:
            for function_code in args.functions:
                row: dict[str, Any] = {
                    "host": args.host,
                    "port": port,
                    "unit_id": unit_id,
                    "function_code": function_code,
                    "address": args.address,
                    "count": args.count,
                }
                try:
                    row["registers"] = client.read_registers(unit_id, args.address, args.count, function_code)
                    row["ok"] = True
                except Exception as error:
                    row["ok"] = False
                    row["error"] = str(error)
                results.append(row)
                print(json.dumps(row, ensure_ascii=False))
        client.close()
    successes = sum(1 for row in results if row["ok"])
    print(json.dumps({"summary": {"attempts": len(results), "successes": successes}}, ensure_ascii=False))
    return 0 if successes else 2


if __name__ == "__main__":
    raise SystemExit(main())
