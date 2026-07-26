#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import GatewayConfig, load_config
from app.services.gateway_service import GatewayService
from app.storage.sqlite_store import SQLiteStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a complete read-only BMS/PCS extraction validation")
    parser.add_argument("--config", default=os.getenv("KINETICS_CONFIG", "configs/kinetics_hardware_template.json"))
    parser.add_argument("--output", default="hardware_read_validation.json")
    return parser.parse_args()


def point_quality(asset: dict[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for point in asset.get("telemetry", {}).values():
        quality = str(point.get("quality", "unknown")) if isinstance(point, dict) else "unknown"
        result[quality] = result.get(quality, 0) + 1
    return result


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    config.mode = "read_only"
    config.bms.write_enabled = False
    config.pcs.write_enabled = False
    with tempfile.TemporaryDirectory(prefix="kinetics-validation-") as directory:
        config.storage.preferred_root = directory
        config.storage.fallback_root = directory
        config.storage.require_preferred_mount = False
        service = GatewayService(config, SQLiteStore(config.storage))
        snapshot = service.snapshot()
        assets = [
            snapshot["bank"],
            *snapshot["racks"],
            *snapshot["environment"].values(),
            snapshot["pcs"],
        ]
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gateway_id": config.gateway_id,
            "mode": config.mode,
            "network": config.network.model_dump(),
            "bms": config.bms.model_dump(),
            "pcs": config.pcs.model_dump(),
            "assets": [
                {
                    "asset_id": asset.get("asset_id"),
                    "enabled": not bool(asset.get("disabled", False)),
                    "online": asset.get("online"),
                    "point_count": len(asset.get("telemetry", {})),
                    "quality": point_quality(asset),
                    "read_errors": asset.get("read_errors", []),
                    "poll_status": asset.get("poll_status", {}),
                }
                for asset in assets
            ],
            "alarms": snapshot.get("alarms", []),
            "polling": snapshot.get("polling", {}),
            "data_rate": service.data_rate_analysis(),
        }
        Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        failures = [
            asset for asset in report["assets"]
            if asset.get("enabled", True) and not asset["online"]
        ]
        return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
