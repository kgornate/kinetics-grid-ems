# U1.1 UGX Cloud Uploader Key Mapping Patch

## Purpose

U1 proved that the gateway can POST timestamped telemetry to UGX and receive HTTP 200 OK. The first payload used internal gateway key names such as `bess_1_fast_bms_display_soc`. UGX confirmed that the payload structure is correct but that the keys should use their expected flat names, such as `stack_soc`, `rack_soc_r1`, `meter_freq`, and `pcs_pcs_total_active_power_kw_r1`.

U1.1 adds a mapping layer before POST. The uploader still reads the same Fast BESS local historian records, but it now converts internal keys into the expected UGX key plan format.

## Current safe profile

The installed U1.1 template enables the `uniqgrid_v1_1s` mapping profile. This maps the 1-second/high-frequency key set from the UGX key frequency plan:

- envelope fields: `time`, `ts`
- bank fields: `stack_volt`, `stack_curr`, `stack_power`, `stack_soc`
- meter fields: `meter_ua`, `meter_ub`, `meter_uc`, `meter_uab`, `meter_ubc`, `meter_uca`, `meter_ia`, `meter_ib`, `meter_ic`, `meter_in`, `meter_pa`, `meter_pb`, `meter_pc`, `meter_pt`, `meter_freq`
- rack fields: `rack_volt_r1`, `rack_curr_r1`, `rack_power_r1`, `rack_soc_r1`, `pcs_pcs_total_active_power_kw_r1`, and corresponding `r2`, `r3`, `r4` keys

For the current field setup, `bess_1/external_ems_1` maps to `r1`, and `bess_2/external_ems_2` maps to `r2`. `r3` and `r4` are included as expected keys with null values unless later mapped to real devices.

## What stays disabled

Full PCS+BMS snapshot upload remains disabled by default because it previously caused local API timeout under load. First validate the corrected Fast BESS mapped payload with UGX. Then enable/tune slower full PCS+BMS later.

## Test command

```bash
cd /root/kinetics-grid-ems/northbound_ems_gateway
export PYTHONPATH=/root/kinetics-grid-ems/northbound_ems_gateway/src
export NB_EMS_INTERNAL_PASSWORD='Internal@123'

python3 tools/ugx_dump_mapped_payload_sample.py \
  --config configs/ugx_cloud_uploader.json \
  --records 5 \
  --output /tmp/ugx_mapped_payload_sample_5_records.json

python3 -m nb_ems_gateway.ugx_uploader.main \
  --config configs/ugx_cloud_uploader.json \
  --once \
  --dry-run
```

## First live retest

After confirming the dry-run key names are correct:

```bash
python3 -m nb_ems_gateway.ugx_uploader.main \
  --config configs/ugx_cloud_uploader.json \
  --once \
  --live
```

Ask UGX to confirm that the data is now visible under the expected keys.
