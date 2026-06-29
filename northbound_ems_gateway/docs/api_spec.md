# NorthBound EMS Gateway API Spec - Read-Only v0.2

The API is intentionally read-only. It exposes decoded telemetry, asset summaries, register map metadata, health state, alarms, and local historian data. It does not expose command or register-write endpoints.

## Asset APIs

| Endpoint | Purpose |
|---|---|
| `GET /api/assets` | List asset summaries, online state, signal counts, and key signals. |
| `GET /api/assets/{asset_id}` | Get one asset summary without full telemetry. |
| `GET /api/assets/{asset_id}/telemetry` | Get full latest telemetry for one asset. |
| `GET /api/assets/{asset_id}/telemetry?category=soc_soh` | Get latest telemetry filtered by category. |
| `GET /api/assets/{asset_id}/key-signals` | Get only dashboard-grade key signals. |
| `GET /api/telemetry` | Get all asset snapshots. |
| `GET /api/telemetry/key-signals` | Get key signals for all assets. |

Supported asset IDs are:

```text
existing_ems
bms_1
pcs_1
utility_meter
fire_protection
liquid_cooling
dehumidifier
io_module
remote_status
```

## Register map APIs

| Endpoint | Purpose |
|---|---|
| `GET /api/registers/map` | Register map summary, entities, assets, poll groups, categories, and key signals. |
| `GET /api/registers/raw` | Paginated register list. |
| `GET /api/registers/raw?asset_id=bms_1` | Register list filtered by asset. |
| `GET /api/registers/raw?asset_id=bms_1&key_only=true` | Key register list filtered by asset. |
| `GET /api/registers/raw?category=insulation` | Register list filtered by dashboard category. |

## Storage APIs

| Endpoint | Purpose |
|---|---|
| `GET /api/storage/status` | SQLite historian status and row counts. |
| `GET /api/storage/snapshots?asset_id=bms_1&limit=10` | Latest stored asset snapshots. |
| `GET /api/storage/points?asset_id=bms_1&signal_name=soc.display_percent&limit=100` | Historical point values for one signal. |

## WebSocket

| Endpoint | Purpose |
|---|---|
| `WS /ws/telemetry` | Sends latest telemetry snapshot once per second for local Flutter/dashboard use. |

## Safety rule

There are no `POST /api/commands`, `POST /api/write-register`, `POST /api/start`, `POST /api/stop`, or similar write endpoints in this version.

## Server upload diagnostics APIs - v0.3

These APIs are for monitoring and testing the HTTPS REST upload service. They do not write to the Chinese EMS.

### GET `/api/server-upload/status`

Returns current uploader state:

```json
{
  "enabled": true,
  "transport": "https_rest",
  "endpoint_url": "https://server.example.com/api/v1/gateway/telemetry",
  "network_interface": "mlan0",
  "source_ip": "192.168.88.21",
  "payload_mode": "key_signals",
  "upload_interval_sec": 10,
  "queue_size": 0,
  "success_count": 15,
  "failure_count": 0,
  "last_attempt_utc": "2026-06-29T10:20:00Z",
  "last_success_utc": "2026-06-29T10:20:00Z",
  "last_error": null,
  "last_status_code": 200,
  "running": true
}
```

### POST `/api/server-upload/upload-once`

Triggers one manual upload attempt using the latest read-only telemetry snapshot. This is intended for commissioning and backend testing.

