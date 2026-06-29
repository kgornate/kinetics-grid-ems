#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nb_ems_gateway.dictionary.excel_parser import parse_excel_register_map
from nb_ems_gateway.dictionary.map_loader import save_register_map


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate JSON register map from EMS north-bound Excel file")
    parser.add_argument("--input", required=True, help="Input Excel file path")
    parser.add_argument("--output", required=True, help="Output JSON register map path")
    parser.add_argument("--name", default="china_ems_northbound")
    parser.add_argument("--version", default="v1")
    args = parser.parse_args()

    register_map = parse_excel_register_map(args.input, name=args.name, version=args.version)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    save_register_map(register_map, output)
    print(f"Generated {output} with {register_map.point_count} points")
    print(f"Address range: {register_map.min_address}..{register_map.max_address}")
    print("Entities:")
    for entity in register_map.entities():
        print(f"  - {entity}: {len(register_map.by_entity(entity))}")


if __name__ == "__main__":
    main()
