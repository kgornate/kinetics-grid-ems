#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nb_ems_gateway.config.loader import load_config
from nb_ems_gateway.protocol.modbus_client import ReadOnlyModbusClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Test read-only Modbus TCP connection to Chinese EMS")
    parser.add_argument("--config", default="configs/site_template.json")
    parser.add_argument("--address", type=int, default=0)
    parser.add_argument("--count", type=int, default=2)
    args = parser.parse_args()

    config = load_config(args.config)
    client = ReadOnlyModbusClient(config.existing_ems)
    regs = client.read_registers(args.address, args.count)
    print(f"Connected. Read address={args.address}, count={args.count}: {regs}")
    client.close()


if __name__ == "__main__":
    main()
