from __future__ import annotations

import argparse
import json
from nb_ems_gateway.ugx_uploader.config import load_uploader_config
from nb_ems_gateway.ugx_uploader.frequency_plan import UGXFrequencyPlan
from nb_ems_gateway.ugx_uploader.state_store import UploaderStateStore


def main() -> None:
    p = argparse.ArgumentParser(description="Show UGX uploader local state")
    p.add_argument("--config", default="configs/ugx_cloud_uploader.json")
    args = p.parse_args()
    cfg = load_uploader_config(args.config)
    state = UploaderStateStore(cfg.state_db_path)
    freq_counts = None
    try:
        if cfg.ugx_frequency_upload.enabled:
            freq_counts = UGXFrequencyPlan(cfg.ugx_frequency_upload.key_plan_path).counts_by_frequency()
    except Exception as exc:
        freq_counts = {"error": str(exc)}
    try:
        print(json.dumps({
            "enabled": cfg.enabled,
            "dry_run": cfg.dry_run,
            "telemetry_url": cfg.ugx_server.telemetry_url,
            "fast_bess_upload_enabled": cfg.fast_bess_upload.enabled,
            "full_pcs_bms_upload_enabled": cfg.full_pcs_bms_upload.enabled,
            "ugx_frequency_upload_enabled": cfg.ugx_frequency_upload.enabled,
            "ugx_frequency_enabled_frequencies_sec": cfg.ugx_frequency_upload.enabled_frequencies_sec,
            "ugx_frequency_allow_large_3600_upload": cfg.ugx_frequency_upload.allow_large_3600_upload,
            "ugx_frequency_frequency_key_aliases": cfg.ugx_frequency_upload.frequency_key_aliases,
            "ugx_frequency_plan_counts": freq_counts,
            "ugx_combined_upload_enabled": cfg.ugx_combined_upload.enabled,
            "ugx_combined_cloud_post_interval_sec": cfg.ugx_combined_upload.cloud_post_interval_sec,
            "ugx_combined_include_fast_bess": cfg.ugx_combined_upload.include_fast_bess,
            "ugx_combined_include_frequency_profiles": cfg.ugx_combined_upload.include_frequency_profiles,
            "ugx_combined_max_records_per_post": cfg.ugx_combined_upload.max_records_per_post,
            "ugx_combined_max_payload_bytes": cfg.ugx_combined_upload.max_payload_bytes,
            "ugx_key_mapping_enabled": cfg.ugx_key_mapping.enabled,
            "ugx_key_mapping_profile": cfg.ugx_key_mapping.profile,
            "emit_unmapped_keys": cfg.ugx_key_mapping.emit_unmapped_keys,
            "state": state.status(),
        }, indent=2))
    finally:
        state.close()


if __name__ == "__main__":
    main()
