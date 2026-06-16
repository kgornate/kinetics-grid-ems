# EMS Web API Contract

## Purpose

This document defines the local Wi-Fi/LAN Web API interface exposed by the i.MX93 EMS Gateway for the web dashboard/frontend/backend team.

This API layer runs in parallel with the existing Flutter dashboard communication.

- Existing Flutter dashboard: UDP + TCP + HTTP over Ethernet
- New web dashboard: REST + SSE over Wi-Fi/LAN

## Base URLs

For Ethernet testing:

```text
http://192.168.10.2:8000
```

For Wi-Fi testing, replace with the i.MX93 Wi-Fi IP:
- Wi-Fi IP: 10.55.41.131

imx93_wifi_ip = 10.55.41.131
```text
http://<imx93_wifi_ip>:8000
```

Existing log APIs remain on port 7000:

```text
http://<imx93_wifi_ip>:7000
```

## Authentication

For local v1 testing, authentication is disabled by default:

```python
WEB_API_ENABLE_AUTH = False
```

When enabled later, command APIs require:

```http
X-API-Key: <configured-api-key>
```

## Gateway APIs

### Health

```http
GET /api/gateway/health
```

Expected response:

```json
{
  "status": "ok",
  "server": "ems_web_api_server",
  "message": "EMS Web API server running",
  "timestamp": "2026-06-01T12:30:00+05:30",
  "host": "0.0.0.0",
  "port": 8000
}
```

### Gateway Status

```http
GET /api/gateway/status
```

Returns gateway mode, enabled assets, network ports, existing UDP/TCP/log server status, and web API status.

### Gateway Network

```http
GET /api/gateway/network
```

Returns configured EMS network service details. Actual Wi-Fi/Ethernet IP assignment is handled by Linux OS, not by `main.py`.

## Asset APIs

### Get All Assets

```http
GET /api/assets
```

Expected response shape:

```json
{
  "status": "ok",
  "gateway_id": "imx93_gateway_1",
  "timestamp": "2026-06-01T12:30:00+05:30",
  "assets_count": 3,
  "assets": [
    {
      "asset_id": "bms_1",
      "asset_key": "bms",
      "asset_type": "bms",
      "protocol": "modbus_tcp",
      "enabled": true,
      "running": true,
      "online": true
    },
    {
      "asset_id": "pcs_1",
      "asset_key": "pcs",
      "asset_type": "pcs",
      "protocol": "modbus_tcp",
      "enabled": true,
      "running": true,
      "online": true
    },
    {
      "asset_id": "chiller_1",
      "asset_key": "chiller",
      "asset_type": "chiller",
      "protocol": "modbus_rtu",
      "enabled": true,
      "running": true,
      "online": true
    }
  ]
}
```

### Get Single Asset

```http
GET /api/assets/bms_1
GET /api/assets/pcs_1
GET /api/assets/chiller_1
```

## Latest Telemetry APIs

### Combined Latest Telemetry

```http
GET /api/telemetry/latest
```

This returns the same combined latest telemetry packet used by the existing UDP stream. It is intended as the primary latest-data API for the web dashboard.

### Asset Latest Telemetry

```http
GET /api/assets/bms_1/telemetry/latest
GET /api/assets/pcs_1/telemetry/latest
GET /api/assets/chiller_1/telemetry/latest
```

Expected response shape:

```json
{
  "status": "ok",
  "asset_id": "bms_1",
  "asset_type": "bms",
  "timestamp": "2026-06-01T12:30:00+05:30",
  "online": true,
  "telemetry": {
    "asset_id": "bms_1"
  }
}
```

## Telemetry Keys API

```http
GET /api/assets/bms_1/telemetry/keys
GET /api/assets/pcs_1/telemetry/keys
GET /api/assets/chiller_1/telemetry/keys
```

This returns telemetry keys discovered from the latest cached telemetry packet. It also groups keys by broad functional categories where possible.

## Timeseries API from Local Logs

```http
GET /api/assets/{asset_id}/telemetry/timeseries?keys=key1,key2&date=YYYY-MM-DD&limit=100
```

Example:

```http
GET /api/assets/bms_1/telemetry/timeseries?keys=stack_voltage_v,stack_soc_percent&date=2026-06-01&limit=100
```

This API reads from the existing local CSV logs through `LogQueryService` and reshapes rows into a web-dashboard-friendly timeseries format.

Expected response shape:

```json
{
  "status": "ok",
  "asset_id": "bms_1",
  "date": "2026-06-01",
  "keys": ["stack_voltage_v", "stack_soc_percent"],
  "data": {
    "stack_voltage_v": [
      {"ts": 1777577373325, "value": "712.5"}
    ],
    "stack_soc_percent": [
      {"ts": 1777577373325, "value": "78.4"}
    ]
  },
  "source": "local_csv_logs"
}
```

## Command APIs

### Generic Command API

```http
POST /api/commands
Content-Type: application/json
```

Example:

```json
{
  "asset_id": "chiller_1",
  "command": "SET_TEMP",
  "value": 25.0
}
```

### Asset-Specific Command APIs

```http
POST /api/assets/bms_1/commands
POST /api/assets/pcs_1/commands
POST /api/assets/chiller_1/commands
```

Chiller example:

```json
{
  "command": "SET_TEMP",
  "value": 25.0
}
```

PCS example:

```json
{
  "command": "PCS_SET_ACTIVE_POWER",
  "value": 20.0
}
```

BMS example:

```json
{
  "command": "START_BMS_PRECHARGE"
}
```

Command responses include `status`, `asset_id`, `command`, `request_id`, and the existing command result returned by `main.py -> execute_command()`.

## SSE Live Telemetry Stream

```http
GET /api/stream/telemetry
```

Frontend example:

```javascript
const events = new EventSource("http://<imx93_wifi_ip>:8000/api/stream/telemetry");

events.addEventListener("telemetry", (event) => {
  const telemetry = JSON.parse(event.data);
  console.log("Live EMS telemetry:", telemetry);
});

events.onerror = (error) => {
  console.error("EMS telemetry stream error", error);
};
```

## Existing Log/Event APIs

These remain available on port 7000:

```http
GET /api/health
GET /api/storage/status?asset_id=bms_1
GET /api/logs/assets
GET /api/logs/files?asset_id=bms_1
GET /api/logs/telemetry?asset_id=bms_1&date=YYYY-MM-DD&limit=100
GET /api/logs/events?asset_id=pcs_1&limit=100
GET /api/logs/errors?asset_id=chiller_1&limit=100
GET /api/logs/metadata
```

## Error Format

```json
{
  "status": "error",
  "error_code": "INVALID_ASSET",
  "message": "Asset not found: bms_2",
  "timestamp": "2026-06-01T12:30:00+05:30"
}
```
