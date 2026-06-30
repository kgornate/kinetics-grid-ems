# NorthBound EMS Gateway v0.5

Read-only NorthBound EMS Gateway for the China-supplied EMS Modbus TCP register map.

v0.5 includes all previous v0.4 features and adds SD-card-safe storage protection.

## Included features

- Read-only northbound Modbus TCP polling
- 1421-point protocol dictionary generated from the supplied north-bound register sheet
- Asset APIs on port 8000
- WebSocket telemetry on `/ws/telemetry`
- SQLite historian
- HTTPS REST server upload from v0.3
- Kinetics-style logs and filters from v0.4
- Separate logs API on port 7000
- v0.5 storage protection for external SD card logging

## Default storage path

v0.5 expects logs/history on the external SD card:

```text
/mnt/ems-logs/northbound_ems_gateway/nb_ems_gateway.db
```

Before starting the gateway, confirm:

```bash
df -h /mnt/ems-logs
findmnt /mnt/ems-logs
```

## Run on i.MX93

```bash
cd ~/kinetics-grid-ems/northbound_ems_gateway_v0_5_storage_protection
PYTHONPATH=src python3 -m nb_ems_gateway.main --config configs/development.json --mock
```

## Main APIs

```text
GET /api/health
GET /api/assets
GET /api/telemetry
GET /api/telemetry/key-signals
GET /api/assets/{asset_id}/telemetry
GET /api/alarms
WS  /ws/telemetry
```

## Logs and filters

Available on both port 8000 and port 7000:

```text
GET  /api/logs
GET  /api/logs?severity=warning
GET  /api/logs?event_type=poll_point_failed
GET  /api/logs?source=server_upload
GET  /api/logs?asset_id=bms_1
GET  /api/logs?search=upload
GET  /api/logs/summary
GET  /api/logs/filters
GET  /api/logs/export.csv
POST /api/logs/test
```

## Storage protection APIs

```text
GET  /api/storage/health
GET  /api/storage/status
POST /api/storage/cleanup
POST /api/storage/vacuum
GET  /api/storage/snapshots
GET  /api/storage/points
```

## v0.5 storage config

```json
"storage": {
  "enabled": true,
  "type": "sqlite",
  "path": "/mnt/ems-logs/northbound_ems_gateway/nb_ems_gateway.db",
  "required_mount_path": "/mnt/ems-logs",
  "fail_if_mount_missing": true,
  "min_free_space_mb": 512,
  "max_db_size_mb": 2048,
  "retention_days": 7,
  "store_mode": "key_signals",
  "snapshot_interval_sec": 30,
  "cleanup_on_startup": true,
  "vacuum_after_cleanup": false
}
```

This means the gateway will not silently write history to the root filesystem if `/mnt/ems-logs` is not mounted.

## Safety

The gateway remains read-only with respect to the Chinese EMS.

```text
No Modbus writes
No control commands
No PCS/BMS start-stop
No charge/discharge writes
```


## v0.5.1 hotfix

- Hardens `/api/health` when storage count/status inspection hits a transient SQLite issue.
- Makes `/api/assets` return `items`, `assets`, and `count` for frontend compatibility.
- Adds Cloudflare-friendly asset detail options:
  - `/api/assets/bms_1/telemetry?compact=true`
  - `/api/assets/bms_1/telemetry?compact=true&page=1&page_size=100`
  - `/api/assets/bms_1/telemetry?key_only=true`
