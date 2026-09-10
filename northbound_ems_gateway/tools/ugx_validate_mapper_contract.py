#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from nb_ems_gateway.ugx_uploader.key_mapper import UGX_EXPECTED_1S_KEYS, UGXKeyMapper
from nb_ems_gateway.ugx_uploader.config import load_uploader_config

FORBIDDEN_FAST_PREFIXES = (
    "cel_",
    "cell_",
    "pole_temp_",
)
FORBIDDEN_FAST_KEYS = {
    "rack_ave_soh_r1",
    "rack_ave_soh_r2",
    "rack_ave_soh_r3",
    "rack_ave_soh_r4",
    "total_cha_cap_r1",
    "total_cha_cap_r2",
    "total_cha_cap_r3",
    "total_cha_cap_r4",
    "total_dis_cap_r1",
    "total_dis_cap_r2",
    "total_dis_cap_r3",
    "total_dis_cap_r4",
    "cluprechgvol_r1",
    "cluprechgvol_r2",
    "cluprechgvol_r3",
    "cluprechgvol_r4",
}


def synthetic_record() -> dict:
    ts = 1786629185618
    v = {
        "external_ems_1_fast_bms_cluster_total_voltage_collected": 862.9,
        "external_ems_1_fast_bms_cluster_total_current": 1.0,
        "external_ems_1_fast_bms_display_soc": 91.6,
        "external_ems_1_fast_pcs_total_active_power": 7.2,
        "external_ems_1_fast_pcs_phase_a_voltage": 238.0,
        "external_ems_1_fast_pcs_phase_b_voltage": 237.0,
        "external_ems_1_fast_pcs_phase_c_voltage": 237.5,
        "external_ems_1_fast_pcs_phase_a_current": 30.7,
        "external_ems_1_fast_pcs_phase_b_current": 29.0,
        "external_ems_1_fast_pcs_phase_c_current": 29.8,
        "external_ems_1_fast_pcs_grid_frequency": 49.94,
        "external_ems_2_fast_bms_cluster_total_voltage_collected": 853.4,
        "external_ems_2_fast_bms_cluster_total_current": 6.6,
        "external_ems_2_fast_bms_display_soc": 55.9,
        "external_ems_2_fast_pcs_total_active_power": 1.7,
        "external_ems_2_fast_pcs_phase_a_voltage": 237.9,
        "external_ems_2_fast_pcs_phase_b_voltage": 237.6,
        "external_ems_2_fast_pcs_phase_c_voltage": 237.2,
        "external_ems_2_fast_pcs_phase_a_current": 0.0,
        "external_ems_2_fast_pcs_phase_b_current": 0.0,
        "external_ems_2_fast_pcs_phase_c_current": 0.0,
        "external_ems_2_fast_pcs_grid_frequency": 49.93,
        # These are deliberately present to prove they cannot leak into fast profile.
        "external_ems_1_full_bms_cell_voltage_1": 3300,
        "external_ems_1_full_bms_battery_temperature_1": 24.0,
        "external_ems_1_full_bms_soh": 100,
        "external_ems_1_full_bms_total_cumulative_charge_capacity": 123456,
    }
    return {"ts": ts, "values": v}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Validate UGX mapper output contracts without touching cloud APIs")
    parser.add_argument("--config", default="configs/ugx_cloud_uploader.json")
    parser.add_argument("--output", default="/tmp/ugx_mapper_contract_validation.json")
    args = parser.parse_args()

    cfg = load_uploader_config(args.config)
    cfg.ugx_key_mapping.enabled = True
    cfg.ugx_key_mapping.profile = "uniqgrid_v1_1s"
    mapper = UGXKeyMapper(cfg.ugx_key_mapping)

    fast = mapper.map_fast_1s_record(synthetic_record())
    values = fast.get("values") or {}
    keys = list(values.keys())
    forbidden = [k for k in keys if k.startswith(FORBIDDEN_FAST_PREFIXES) or k in FORBIDDEN_FAST_KEYS]
    missing = [k for k in UGX_EXPECTED_1S_KEYS if k not in values]
    extra = [k for k in keys if k not in UGX_EXPECTED_1S_KEYS]

    result = {
        "fast_key_count": len(keys),
        "expected_fast_key_count": len(UGX_EXPECTED_1S_KEYS),
        "missing_expected_keys": missing,
        "extra_keys": extra,
        "forbidden_fast_keys": forbidden,
        "ok": len(keys) == len(UGX_EXPECTED_1S_KEYS) and not missing and not extra and not forbidden,
        "fast_keys": keys,
    }
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)
    print("FAST_41_MAPPER_CONTRACT_OK")


if __name__ == "__main__":
    main()
