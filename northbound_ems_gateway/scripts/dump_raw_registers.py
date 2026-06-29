#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nb_ems_gateway.config.loader import load_config
from nb_ems_gateway.protocol.modbus_client import ReadOnlyModbusClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump raw registers from existing EMS")
    parser.add_argument("--config", default="configs/site_template.json")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--output")
    args = parser.parse_args()

    config = load_config(args.config)
    client = ReadOnlyModbusClient(config.existing_ems)
    regs = client.read_registers(args.start, args.count)
    payload = {"start": args.start, "count": args.count, "registers": regs}
    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Saved {args.output}")
    else:
        print(json.dumps(payload, indent=2))
    client.close()


if __name__ == "__main__":
    main()
