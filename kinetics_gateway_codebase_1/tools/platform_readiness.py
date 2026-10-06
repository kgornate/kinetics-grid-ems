#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import load_config
from app.services.platform_readiness import platform_readiness


def main() -> int:
    parser = argparse.ArgumentParser(description="Report Ornate EMS software/field commissioning readiness without writes")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    result = platform_readiness(load_config(args.config))
    print(json.dumps(result, indent=2))
    return 0 if not result["hardware_control_armed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
