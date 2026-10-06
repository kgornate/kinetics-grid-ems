# UGX Cloud Uploader U1.2 - Frequency-Based Full PCS/BMS Upload

U1.2 extends the already working UGX uploader with a frequency-aware upload path based on `key_frequency_plan.xlsx`.

## Current stable U1.1 behavior

The existing Fast BESS compact uploader remains the high-frequency path. It continues to post mapped UGX keys such as `stack_volt`, `stack_curr`, `stack_soc`, `meter_*`, and `rack_*_r1/r2` using timestamped records.

## New U1.2 behavior

U1.2 adds `ugx_frequency_upload`, which reads one full PCS/BMS snapshot from the local gateway API only when a slower UGX frequency group is due. It then maps the snapshot into UGX keys and posts only the due group.

Default safe rollout:

- `60s` health/status group is implemented and enabled when `ugx_frequency_upload.enabled=true`.
- `900s` slow-changing group is implemented and enabled when `ugx_frequency_upload.enabled=true`.
- `3600s` heavy cell/rack diagnostic group is implemented but guarded by `allow_large_3600_upload=false` by default.
- `86400s` static/on-change keys are available in the plan but not enabled by default.

## Why 3600s is guarded

The 3600s profile contains 8704 planned keys, mainly cell voltage, cell temperature, cell SOC/SOH, and pole temperature keys across four rack groups. The gateway currently has two live EMS/BESS sources. Rack 3 and rack 4 are kept as null/unmapped unless later added. The 3600s group should be tested separately with UGX before enabling continuous upload.

## Config block

```json
"ugx_frequency_upload": {
  "enabled": false,
  "state_key_prefix": "ugx_frequency",
  "key_plan_path": "data/ugx/key_frequency_plan_v1.json",
  "enabled_frequencies_sec": [60, 900],
  "allow_large_3600_upload": false,
  "include_null_keys": false,
  "always_include_time_fields": true,
  "post_empty_profiles": false,
  "max_keys_per_post": 2500,
  "profile_name": "uniqgrid_frequency_v1_2"
}
```

## Recommended validation flow

1. Keep the continuous U1.1 service stopped during installation.
2. Install U1.2 patch.
3. Generate dry-run samples for 60s and 900s profiles.
4. Enable `ugx_frequency_upload.enabled=true` with `dry_run=true` and run one dry-run cycle.
5. If dry-run is good, set `dry_run=false`, restart the service, and monitor logs.
6. Enable `3600s` only after UGX confirms payload size and server behavior.
