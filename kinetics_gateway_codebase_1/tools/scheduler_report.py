#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_config
from app.services.gateway_service import GatewayService
from app.storage.sqlite_store import SQLiteStore


def main() -> int:
    config = load_config(os.getenv("KINETICS_CONFIG", "configs/kinetics_mock.json"))
    service = GatewayService(config, SQLiteStore(config.storage))
    report = {
        "assets": service.assets(),
        "health": service.health(),
        "data_rate": service.data_rate_analysis(),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
