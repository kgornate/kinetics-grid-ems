#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nb_ems_gateway.dictionary.map_loader import load_register_map


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate generated JSON register map")
    parser.add_argument("path")
    args = parser.parse_args()

    register_map = load_register_map(args.path)
    errors = []
    seen_addresses = set()
    for point in register_map.points:
        if point.register_qty != 2:
            errors.append(f"{point.point_id}: register_qty is {point.register_qty}, expected 2")
        if point.point_type.lower() != "float":
            errors.append(f"{point.point_id}: point_type is {point.point_type}, expected Float")
        if point.software_access != "read_only":
            errors.append(f"{point.point_id}: software_access is not read_only")
        if point.address in seen_addresses:
            errors.append(f"Duplicate address {point.address}")
        seen_addresses.add(point.address)
    print(f"Map: {register_map.name} {register_map.version}")
    print(f"Points: {register_map.point_count}")
    print(f"Address range: {register_map.min_address}..{register_map.max_address}")
    print(f"Entities: {len(register_map.entities())}")
    if errors:
        print("Errors:")
        for error in errors[:100]:
            print(f"  - {error}")
        raise SystemExit(1)
    print("Validation OK")


if __name__ == "__main__":
    main()
