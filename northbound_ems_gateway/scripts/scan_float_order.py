#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nb_ems_gateway.config.loader import load_config
from nb_ems_gateway.decoding.float32_decoder import Float32Decoder
from nb_ems_gateway.protocol.modbus_client import ReadOnlyModbusClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Read two registers and show all float byte/word order interpretations")
    parser.add_argument("--config", default="configs/site_template.json")
    parser.add_argument("--address", type=int, required=True, help="Register address to test, e.g. SOC address")
    args = parser.parse_args()

    config = load_config(args.config)
    client = ReadOnlyModbusClient(config.existing_ems)
    regs = client.read_registers(args.address, 2)
    print(f"Raw registers at {args.address}: {regs}")
    for order in ["ABCD", "CDAB", "BADC", "DCBA"]:
        try:
            value = Float32Decoder(order).decode((regs[0], regs[1]))
            print(f"{order}: {value}")
        except Exception as exc:
            print(f"{order}: ERROR {exc}")
    client.close()


if __name__ == "__main__":
    main()
