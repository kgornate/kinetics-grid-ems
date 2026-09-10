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

## v0.6 authentication update

v0.6 adds gateway-enforced login/authentication for both local eth0 access and Cloudflare remote access.

### Default demo users

These passwords are for initial integration testing only. Change them before customer handover.

```text
Customer account:
  username: customer
  password: Customer@123
  role: customer_admin

Internal account:
  username: internal
  password: Internal@123
  role: internal_admin
```

### Login flow used by Flutter and IT web

```bash
curl -X POST http://192.168.10.2:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"customer","password":"Customer@123"}'
```

The response contains an access token:

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "expires_in_sec": 28800,
  "username": "customer",
  "role": "customer_admin",
  "display_name": "Customer Admin"
}
```

Every protected API request must include the token:

```bash
curl http://192.168.10.2:8000/api/health \
  -H "Authorization: Bearer <access_token>"
```

The same flow works through Cloudflare:

```bash
curl -X POST https://ems-api.unityess.cloud/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"customer","password":"Customer@123"}'
```

### WebSocket telemetry with token

```text
ws://192.168.10.2:8000/ws/telemetry?token=<access_token>
wss://ems-api.unityess.cloud/ws/telemetry?token=<access_token>
```

### Role model

```text
customer_admin:
  - monitoring APIs
  - logs/events APIs
  - storage and internal diagnostics APIs
  - customer-safe runtime config update APIs

internal_admin:
  - full internal/engineering access
  - intended for commissioning, debugging, and future command/control APIs
```

### Runtime config APIs

```text
GET  /api/config/runtime
POST /api/config/runtime
```

Example:

```bash
curl -X POST http://192.168.10.2:8000/api/config/runtime \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"section":"storage","values":{"retention_days":14,"snapshot_interval_sec":60}}'
```

These updates are runtime updates. They are logged in gateway events for audit/debugging. Persisting them back to a site JSON config can be added later if needed.

### Changing passwords

Generate a new password hash:

```bash
cd northbound_ems_gateway
PYTHONPATH=src python3 tools/generate_password_hash.py
```

Then replace the corresponding `auth.users[].password_hash` value in the selected config JSON. Also change `auth.jwt_secret` or set `NB_EMS_JWT_SECRET` in the service environment before deployment.

---

## v1.2 Multi-Source Control Update

This package supports two independent Chinese EMS/BESS units over the same `eth1` network and the same Modbus TCP protocol map.

| Source ID | IP | Port | Unit ID |
| --- | --- | --- | --- |
| `external_ems_1` | `192.168.100.151` | `502` | `1` |
| `external_ems_2` | `192.168.100.153` | `502` | `1` |

The active register map is:

```text
data/register_maps/unity261pv_modbus_north_v1.json
```

The main control registers are:

```text
42  = manual_charge_value_setting
44  = manual_discharge_value_setting
164 = on_off_grid_switching, 1 = grid-tied, 2 = off-grid
180 = pcs_on_off_grid_status, 0 = off-grid, 1 = on-grid
346 = phase_a_voltage
348 = phase_b_voltage
350 = phase_c_voltage
```

Command-line control helper:

```bash
python3 tools/control_cli.py --base-url http://127.0.0.1:8000 sources
python3 tools/control_cli.py --base-url http://127.0.0.1:8000 grid-mode external_ems_1 grid_tied
python3 tools/control_cli.py --base-url http://127.0.0.1:8000 grid-mode external_ems_1 off_grid
python3 tools/control_cli.py --base-url http://127.0.0.1:8000 charge external_ems_1 50
python3 tools/control_cli.py --base-url http://127.0.0.1:8000 discharge external_ems_2 50
python3 tools/control_cli.py --base-url http://127.0.0.1:8000 site-grid-mode off_grid --order external_ems_1 external_ems_2
```

See `docs/v1_2_multi_source_control_handoff.md` for complete API and test details.
