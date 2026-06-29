# HTTPS REST Server Upload

The NorthBound EMS Gateway v0.3 adds a background HTTPS REST uploader. This is still a read-only gateway with respect to the Chinese EMS. The uploader only sends normalized telemetry/health/alarm data to an external backend server.

## Current network design

- `eth1`: field-side network for Chinese EMS Modbus TCP.
- `eth0`: application-side network for Flutter dashboard and/or Ethernet server uplink.
- `mlan0`: Wi-Fi uplink. v0.3 is configured to use this by default for server upload.

The upload interface is fully config-driven. To change upload from Wi-Fi to Ethernet, change only:

```json
"server_upload": {
  "network_interface": "eth0"
}
```

If `bind_to_interface_source_ip` is true, the uploader resolves the IPv4 address on the selected interface and binds the HTTPS client socket to that source IP.

## Config block

```json
"server_upload": {
  "enabled": true,
  "transport": "https_rest",
  "endpoint_url": "https://your-server.example.com/api/v1/gateway/telemetry",
  "api_key": "YOUR_TOKEN",
  "network_interface": "mlan0",
  "source_ip": null,
  "bind_to_interface_source_ip": true,
  "upload_interval_sec": 10,
  "timeout_sec": 5,
  "payload_mode": "key_signals",
  "buffer_when_offline": true,
  "max_queue_size": 1000,
  "verify_tls": true
}
```

## Backend endpoint expected by the gateway

The gateway sends:

```text
POST /api/v1/gateway/telemetry
Content-Type: application/json
Authorization: Bearer <api_key>
X-Gateway-ID: <gateway_id>
```

The backend should return any `2xx` status on success.

## Payload modes

- `key_signals`: compact payload for cloud dashboards. Recommended default.
- `full_snapshot`: sends all normalized telemetry points for all assets.

## Gateway diagnostics APIs

```text
GET  /api/server-upload/status
POST /api/server-upload/upload-once
GET  /api/health
```

`POST /api/server-upload/upload-once` does not write to the Chinese EMS. It only triggers one HTTPS upload of the latest read-only snapshot.

## Important safety note

This feature does not enable any EMS control, PCS control, BMS control, or Modbus write. `commands_enabled` remains false and the Modbus client remains read-only.

## Example backend receiver

A minimal backend receiver is included for lab testing:

```text
examples/backend_receiver/receiver.py
```

It exposes:

```text
POST /api/v1/gateway/telemetry
GET  /health
```

For real deployment, place the backend behind HTTPS. For local testing, plain HTTP can be used by setting `verify_tls` appropriately and using an `http://` endpoint.
