# NorthBound Gateway Authentication and IT API Usage

## Purpose

The gateway now enforces login at the FastAPI layer. Flutter and the customer/IT web client use the same API flow.

## Users and roles

Two users are configured in the selected gateway config JSON.

| User | Role | Intended use |
|---|---|---|
| `customer` | `customer_admin` | Customer/IT access |
| `internal` | `internal_admin` | Unity ESS / engineering access |

Default demo passwords in the template configs are only for first testing and must be changed before handover.

## Login

```bash
curl -X POST https://ems-api.unityess.cloud/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"customer","password":"Customer@123"}'
```

## Use token

```bash
curl https://ems-api.unityess.cloud/api/health \
  -H "Authorization: Bearer <access_token>"
```

The same URLs work locally by replacing the base URL:

```text
http://192.168.10.2:8000
```

## Main read APIs

```text
GET /api/health
GET /api/assets
GET /api/assets/{asset_id}
GET /api/assets/{asset_id}/telemetry
GET /api/telemetry
GET /api/telemetry/key-signals
GET /api/alarms
GET /api/logs
GET /api/logs/summary
GET /api/logs/filters
GET /api/storage/status
GET /api/storage/health
GET /api/storage/snapshots
GET /api/storage/points
GET /api/registers/map
GET /api/registers/raw
GET /api/server-upload/status
GET /api/config/runtime
```

## Customer-safe config update API

```text
POST /api/config/runtime
```

Example:

```bash
curl -X POST https://ems-api.unityess.cloud/api/config/runtime \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"section":"storage","values":{"retention_days":14}}'
```

Allowed runtime-update sections:

```text
polling
logging
storage
server_upload
```

The update is applied in memory and logged in `gateway_events`. Persistent config-file writeback is intentionally not enabled in this version.

## WebSocket

```text
wss://ems-api.unityess.cloud/ws/telemetry?token=<access_token>
```

## Error meanings

| HTTP status | Meaning |
|---|---|
| 401 | Missing, invalid, or expired token |
| 403 | Valid token but role is not allowed |
| 503 | Backend service such as storage is disabled/unavailable |
