from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from nb_ems_gateway.ugx_uploader.config import load_uploader_config
from nb_ems_gateway.ugx_uploader.fast_bess_adapter import FastBESSAdapter
from nb_ems_gateway.ugx_uploader.key_mapper import UGXKeyMapper


def latest_start_timestamp(db_path: str, sample_count: int) -> int:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30.0)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT timestamp_epoch_ms
            FROM fast_bess_samples
            ORDER BY timestamp_epoch_ms DESC
            LIMIT ?
            """,
            (max(1, int(sample_count)),),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return 0
    return min(int(row[0]) for row in rows) - 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump a UGX-mapped Fast BESS payload sample without posting it")
    parser.add_argument("--config", default="configs/ugx_cloud_uploader.json")
    parser.add_argument("--records", type=int, default=5)
    parser.add_argument("--output", default="/tmp/ugx_mapped_payload_sample_5_records.json")
    args = parser.parse_args()

    cfg = load_uploader_config(args.config)
    start_ts = latest_start_timestamp(cfg.fast_bess_upload.db_path, args.records)
    adapter = FastBESSAdapter(cfg)
    cfg.fast_bess_upload.max_source_rows_per_cycle = max(args.records * 4, 20)
    records, _ = adapter.fetch_records_after(start_ts)
    records = records[-args.records:]
    records = UGXKeyMapper(cfg.ugx_key_mapping).map_records(records)

    out = Path(args.output)
    out.write_text(json.dumps(records, indent=2), encoding="utf-8")

    key_preview = []
    if records:
        key_preview = list((records[0].get("values") or {}).keys())[:80]
    print(json.dumps({
        "output": str(out),
        "records": len(records),
        "mapping_enabled": cfg.ugx_key_mapping.enabled,
        "profile": cfg.ugx_key_mapping.profile,
        "first_record_key_count": len((records[0].get("values") or {}) if records else {}),
        "first_record_keys_preview": key_preview,
    }, indent=2))


if __name__ == "__main__":
    main()
