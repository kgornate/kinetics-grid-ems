from __future__ import annotations

import argparse
import json
from pathlib import Path

from nb_ems_gateway.ugx_uploader.config import load_uploader_config
from nb_ems_gateway.ugx_uploader.frequency_plan import UGXFrequencyPlan
from nb_ems_gateway.ugx_uploader.full_pcs_bms_adapter import FullPCSBMSAdapter
from nb_ems_gateway.ugx_uploader.key_mapper import UGXKeyMapper


def main() -> None:
    p = argparse.ArgumentParser(description="Build a UGX frequency-based full PCS/BMS payload sample from live local gateway data")
    p.add_argument("--config", default="configs/ugx_cloud_uploader.json")
    p.add_argument("--frequency", type=int, default=60, help="UGX frequency group to build, for example 60, 900, 3600, or 86400")
    p.add_argument("--output", default="/tmp/ugx_frequency_payload_sample.json")
    p.add_argument("--include-null-keys", action="store_true")
    args = p.parse_args()

    cfg = load_uploader_config(args.config)
    plan = UGXFrequencyPlan(cfg.ugx_frequency_upload.key_plan_path)
    keys = plan.keys_for_frequency(args.frequency)
    if not keys:
        raise SystemExit(f"No keys found for frequency {args.frequency}")

    record = FullPCSBMSAdapter(cfg).build_snapshot_record()
    mapped = UGXKeyMapper(cfg.ugx_key_mapping).map_record_for_keys(
        record,
        keys,
        include_null_keys=bool(args.include_null_keys or cfg.ugx_frequency_upload.include_null_keys),
        always_include_time_fields=cfg.ugx_frequency_upload.always_include_time_fields,
    )
    out = Path(args.output)
    out.write_text(json.dumps([mapped], indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(out),
        "frequency": args.frequency,
        "planned_key_count": len(keys),
        "value_count": len(mapped.get("values") or {}),
        "keys_preview": list((mapped.get("values") or {}).keys())[:80],
    }, indent=2))


if __name__ == "__main__":
    main()
