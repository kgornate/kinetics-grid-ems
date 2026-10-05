#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.assets.bms_driver import BmsModbusDriver
from app.assets.pcs_driver import PcsModbusDriver
from app.core.catalog import ProtocolCatalog, apply_pcs_overrides
from app.core.config import load_config, resolve_path
from app.services.normalized_views import build_normalized_snapshot


def _asset_ok(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": asset.get("asset_id"),
        "online": asset.get("online"),
        "host": asset.get("host"),
        "port": asset.get("port"),
        "unit_id": asset.get("unit_id"),
        "point_count": len(asset.get("telemetry", {})),
        "read_errors": asset.get("read_errors", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase-4 Elecod + Lineage read-only commissioning probe. Never writes field devices."
    )
    parser.add_argument(
        "--config",
        default="configs/elecod_lineage_4pair_phase4_readonly_template.json",
        help="Gateway config path",
    )
    parser.add_argument("--include-normal", action="store_true", help="Also read normal-rate BMS points")
    parser.add_argument("--include-bulk", action="store_true", help="Also read bulk cell arrays (slow/heavy)")
    parser.add_argument("--include-aux", action="store_true", help="Read configured auxiliary BMS endpoints")
    parser.add_argument("--output", help="Optional JSON report output path")
    args = parser.parse_args()

    config = load_config(args.config)
    if config.mode != "read_only":
        raise SystemExit("Refusing commissioning probe: config mode must be read_only")
    if config.bms.write_enabled or config.pcs.write_enabled or config.control_sequence.enabled:
        raise SystemExit("Refusing commissioning probe: every write/control gate must be disabled")

    bms_catalog = ProtocolCatalog.load(resolve_path(config.bms_catalog_file))
    pcs_catalog = apply_pcs_overrides(
        ProtocolCatalog.load(resolve_path(config.pcs_catalog_file)),
        resolve_path(config.pcs.overrides_file),
    )
    bms = BmsModbusDriver(config.bms, bms_catalog)
    pcs = PcsModbusDriver(config.pcs, pcs_catalog)

    bms_classes = {"fast"}
    if args.include_normal:
        bms_classes.add("normal")
    if args.include_bulk:
        bms_classes.add("bulk")

    snapshot: dict[str, Any] = {
        "gateway_id": config.gateway_id,
        "mode": config.mode,
        "sequence": 1,
        "timestamp": None,
        "bank": {},
        "racks": [],
        "pcs_devices": {},
        "environment": {},
    }
    report: dict[str, Any] = {
        "safe_read_only": True,
        "config": str(resolve_path(args.config)),
        "bms": {},
        "pcs": {},
        "commissioning_checks": {
            "lineage_float_word_order": config.bms.word_order,
            "lineage_address_offset": config.bms.address_offset,
            "elecod_address_offset": config.pcs.address_offset,
            "elecod_power_sign_validated": config.pcs.power_sign_validated,
            "writes_enabled": False,
        },
    }

    try:
        bank = bms.read_asset_classes("bms_bank", bms_classes)
        snapshot["bank"] = bank
        report["bms"]["system"] = _asset_ok(bank)
        for rack_cfg in config.bms.racks:
            asset_id = f"bms_rack_{rack_cfg.rack_id}"
            rack = bms.read_asset_classes(asset_id, bms_classes)
            snapshot["racks"].append(rack)
            report["bms"][asset_id] = _asset_ok(rack)

        if args.include_aux and config.bms.poll_environment_enabled:
            for asset_id in bms.environment_asset_ids:
                aux = bms.read_asset_classes(asset_id, bms_classes)
                snapshot["environment"][asset_id] = aux
                report["bms"][asset_id] = _asset_ok(aux)

        for device in config.pcs.enabled_devices:
            asset = pcs.read_all(device.asset_id)
            snapshot["pcs_devices"][device.asset_id] = asset
            report["pcs"][device.asset_id] = _asset_ok(asset)

        normalized = build_normalized_snapshot(snapshot, config)
        report["normalized"] = normalized
        report["interpretation"] = {
            "bms": (
                "If System/Rack SOC or voltage is physically impossible, first test the alternate Lineage FLOAT32 word order "
                "and confirm register addressing before changing application code."
            ),
            "pcs": (
                "Phase 4 performs reads only. Positive/negative Elecod active-power direction is intentionally not tested here."
            ),
        }
    finally:
        pcs.close()
        for client in bms.clients.values():
            client.close()

    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    print(text)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
