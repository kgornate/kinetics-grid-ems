from __future__ import annotations

import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NorthBound EMS Gateway")
    parser.add_argument("--config", default="configs/development.json", help="Path to JSON config file")
    parser.add_argument("--mock", action="store_true", help="Run with mock Modbus values instead of real EMS")
    parser.add_argument("--no-api", action="store_true", help="Poll once and exit without starting API server")
    return parser.parse_args()
