# Health Monitoring and Diagnostics API

The gateway now exposes health and diagnostics APIs in addition to telemetry APIs.

Telemetry answers:

```text
What are the latest values?
```

Health answers:

```text
Can I trust this asset/service right now?
Why is something unhealthy?
What should the operator or backend team check?
```

## New Web API endpoints

```text
GET /api/health
GET /api/health/gateway
GET /api/health/assets
GET /api/health/assets/{asset_id}
GET /api/diagnostics
GET /api/diagnostics/assets/{asset_id}
```

Existing endpoints remain unchanged:

```text
GET /api/gateway/health
GET /api/gateway/status
GET /api/telemetry/latest
GET /api/telemetry/operator
GET /api/assets/{asset_id}/telemetry/latest
GET /api/assets/{asset_id}/telemetry/operator
```

## Example URLs on current Wi-Fi IP

```text
http://192.168.88.16:8000/api/health
http://192.168.88.16:8000/api/health/gateway
http://192.168.88.16:8000/api/health/assets
http://192.168.88.16:8000/api/health/assets/pcs_1
http://192.168.88.16:8000/api/health/assets/bms_1
http://192.168.88.16:8000/api/diagnostics
http://192.168.88.16:8000/api/diagnostics/assets/bms_1
```

## Health status values

```text
healthy   -> service/asset is running and latest telemetry looks good
degraded  -> service is running but telemetry/storage/error state indicates warning/error
offline   -> enabled asset/service is not running or communication is failed
disabled  -> asset/service is disabled by config or command-line option
unknown   -> not enough information yet
```

## Asset health response shape

```json
{
  "status": "degraded",
  "asset_id": "bms_1",
  "asset_key": "bms",
  "asset_type": "bms",
  "enabled": true,
  "running": true,
  "online": false,
  "protocol": "modbus_tcp",
  "profile": "simulator_modbus_tcp",
  "vendor": "simulator",
  "connection": {
    "host": "192.168.10.1",
    "port": 502,
    "unit_id": 1
  },
  "last_successful_poll": null,
  "last_error": "Connection refused",
  "consecutive_failures": 0,
  "reason": "Telemetry reports warning, degraded, or error status.",
  "recommended_action": "Check BMS device/simulator at 192.168.10.1:502, network route, firewall, and unit ID.",
  "storage": {
    "status": "healthy"
  }
}
```

## Frontend recommendation for later

When frontend integration starts, add health cards using:

```text
GET /api/health/assets
GET /api/health/assets/{asset_id}
```

Suggested color mapping:

```text
healthy  -> green
degraded -> yellow/orange
offline  -> red
disabled -> grey
unknown  -> grey
```

The frontend does not need to calculate health. It should render the backend health status and recommended action.
