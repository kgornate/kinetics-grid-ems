# UGX Cloud Uploader U1 Patch

## Purpose

This patch adds a separate sidecar service for pushing Northbound EMS Gateway telemetry to the UGX/Uniqgrid server API without disturbing the existing gateway service.

Existing gateway service remains responsible for Modbus polling, local APIs, Flutter dashboard, Fast BESS logger, storage and control logic. The new uploader only reads already available data and posts telemetry to:

`/api/v1/{deviceToken}/telemetry`

Default configured URL:

`https://platform.uniqgrid.com/api/v1/EMSTEST/telemetry`

## Payload format

The uploader uses the timestamped array format:

```json
[
  {
    "ts": 1786450000000,
    "values": {
      "bess_1_fast_pcs_dc_voltage": 860.1,
      "bess_1_fast_bms_display_soc": 71.6
    }
  }
]
```

This same API is used for live and historical/backlog data. The timestamp `ts` is always Unix epoch milliseconds.

## Uploaded profiles

### 1. Fast BESS compact profile

Reads the local SQLite table `fast_bess_samples`. It uploads the already validated 1-second compact PCS/BMS historian profile.

Default key format:

`{bess_id}_fast_{asset}_{signal}`

Examples:

- `bess_1_fast_pcs_dc_voltage`
- `bess_1_fast_pcs_dc_current`
- `bess_1_fast_pcs_grid_frequency`
- `bess_1_fast_bms_display_soc`
- `bess_1_fast_bms_cluster_total_voltage_collected`

### 2. Full PCS/BMS snapshot profile

Reads live PCS and BMS telemetry from the local gateway API and uploads a slower full snapshot.

Default interval: 60 seconds.

Default key format:

`{bess_id}_full_{asset}_{signal}`

Examples:

- `bess_1_full_pcs_dc_voltage`
- `bess_1_full_pcs_phase_a_voltage`
- `bess_1_full_bms_cluster_total_voltage_collected`
- `bess_1_full_bms_cell_voltage_1`

## Important configuration

File:

`configs/ugx_cloud_uploader.json`

By default, `dry_run` is `true`. In dry-run mode, the uploader builds payloads but does not POST to the server.

For live posting, set:

```json
"dry_run": false
```

Full PCS/BMS upload requires access to the authenticated local gateway API. The systemd service reads `/etc/nb_ems_ugx_uploader.conf` if present. Add this file:

```sh
NB_EMS_INTERNAL_PASSWORD='Internal gateway password here'
```

## Install

```sh
cd /root
 tar -xzf northbound_ugx_cloud_uploader_u1_patch_20260812.tar.gz
cd northbound_ugx_cloud_uploader_u1_patch_20260812
sh install_ugx_cloud_uploader_u1.sh
```

## Dry-run test

```sh
cd /root/kinetics-grid-ems/northbound_ems_gateway
export PYTHONPATH=/root/kinetics-grid-ems/northbound_ems_gateway/src
export NB_EMS_INTERNAL_PASSWORD='CHANGE_ME'
python3 -m nb_ems_gateway.ugx_uploader.main --config configs/ugx_cloud_uploader.json --once --dry-run
```

## Start service

```sh
systemctl start northbound-ugx-cloud-uploader.service
journalctl -u northbound-ugx-cloud-uploader.service -f
```

## Enable on boot

Enable only after dry-run and live test are successful.

```sh
systemctl enable northbound-ugx-cloud-uploader.service
```

## Check status

```sh
cd /root/kinetics-grid-ems/northbound_ems_gateway
export PYTHONPATH=/root/kinetics-grid-ems/northbound_ems_gateway/src
python3 tools/ugx_uploader_status.py --config configs/ugx_cloud_uploader.json
systemctl status northbound-ugx-cloud-uploader.service --no-pager -l
```

## Notes

- This patch does not modify the main gateway loop.
- This patch does not poll Modbus again.
- If UGX server or internet is down, gateway operation continues.
- Fast BESS backlog is uploaded using high-water mark tracking.
- Full PCS/BMS snapshot is sent at a slower interval and does not affect the Fast BESS logger.
- The `key_aliases` object in the config can be used later if UGX wants different key names.
