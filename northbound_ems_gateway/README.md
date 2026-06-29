# NorthBound EMS Gateway

Read-only monitoring bridge for an existing Chinese EMS north-bound Modbus TCP protocol.

## Purpose

This gateway runs on FRDM-i.MX93 and reads the existing EMS local north-bound register table over Modbus TCP. It converts raw vendor registers into clean local assets, telemetry, health, alarms, logs, and APIs.

Version 1 is intentionally **read-only**:

- no Modbus write calls
- no command API routes
- no PCS/BMS start/stop control
- no charge/discharge control logic
- no remote schedule writes

## Network intent

- `eth1`: field-side network to the existing Chinese EMS Modbus TCP server.
- `eth0`: application-side network for local Flutter dashboard and/or server/cloud upload.
- `wifi`: optional commissioning/debug/backup uplink.

The Chinese EMS Modbus TCP details from the protocol sheet are:

- Port: `515`
- Unit ID: `1`
- Point type: `Float`
- Register quantity per point: `2`
- Register address range: `0` to `2840`

The EMS IP address is site-specific and must be configured in `configs/actual_site.json`.

## Quick start in mock mode

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_register_map.py --input data/protocol_sources/china_ems_northbound_register_table.xlsx --output data/register_maps/china_ems_northbound_v1.json
python -m nb_ems_gateway.main --config configs/development.json --mock
```

Then open:

```text
http://127.0.0.1:8000/api/health
http://127.0.0.1:8000/api/assets
http://127.0.0.1:8000/api/alarms
http://127.0.0.1:8000/api/registers/map
```

## Real EMS mode

Update `configs/actual_site.json`:

```json
{
  "existing_ems": {
    "host": "192.168.1.100",
    "port": 515,
    "unit_id": 1,
    "register_function": "holding_registers"
  }
}
```

Then run:

```bash
python -m nb_ems_gateway.main --config configs/actual_site.json
```

## Safety policy

`ReadOnlyModbusClient` does not implement public write methods. Any future write feature must be developed as a separate milestone with allowlists, interlocks, audit logs, and readback verification.

## v0.2 read-only milestone update

This package now includes the Milestone 4 and Milestone 5 read-only foundation:

- Asset-wise telemetry API for `existing_ems`, `bms_1`, `pcs_1`, `utility_meter`, `fire_protection`, `liquid_cooling`, `dehumidifier`, `io_module`, and `remote_status`.
- Dashboard-grade key signals and categories in the generated register map.
- Curated normalization file at `data/normalization/curated_signal_map.json`.
- SQLite local historian for asset snapshots, telemetry points, and gateway events.
- Storage APIs for latest snapshots and point history.
- Read-only WebSocket telemetry stream at `/ws/telemetry`.

The gateway remains strictly read-only. Command routes and Modbus write operations are still intentionally absent.

### Important read-only API endpoints

```text
GET /api/health
GET /api/assets
GET /api/assets/{asset_id}
GET /api/assets/{asset_id}/telemetry
GET /api/assets/{asset_id}/telemetry?category=soc_soh
GET /api/assets/{asset_id}/key-signals
GET /api/telemetry
GET /api/telemetry/key-signals
GET /api/alarms
GET /api/registers/map
GET /api/registers/raw?asset_id=bms_1&key_only=true
GET /api/storage/status
GET /api/storage/snapshots?asset_id=bms_1&limit=10
GET /api/storage/points?asset_id=bms_1&signal_name=soc.display_percent&limit=100
WS  /ws/telemetry
```

### Current milestone status

```text
Milestone 1: Done - protocol dictionary generated from Excel.
Milestone 2: Set aside for now - full fake TCP Modbus server can be completed later.
Milestone 3: Pending - requires real Chinese EMS IP/network access.
Milestone 4: Done for read-only API foundation - asset telemetry, key signals, categories, register filters.
Milestone 5: Done for local logging foundation - SQLite snapshots, point history, event log, dashboard-ready APIs.
```

## v0.3 HTTPS REST server upload update

This package adds a configurable background server uploader. It sends read-only normalized telemetry, gateway health, and alarms to a backend server over HTTPS REST. This does not enable Modbus writes or any PCS/BMS/EMS control command.

Default intended upload interface for v0.3:

```text
mlan0 = Wi-Fi server upload/uplink
```

To switch server upload from Wi-Fi to Ethernet later, change only this config field:

```json
"server_upload": {
  "network_interface": "eth0"
}
```

The server uploader config is:

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

New server upload diagnostics APIs:

```text
GET  /api/server-upload/status
POST /api/server-upload/upload-once
```

`POST /api/server-upload/upload-once` only pushes one read-only telemetry snapshot to the configured backend. It does not write to the Chinese EMS.

A Wi-Fi upload template is provided at:

```text
configs/server_upload_wifi_template.json
```

More details are in:

```text
docs/server_upload_https.md
```
