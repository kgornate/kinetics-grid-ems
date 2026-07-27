# Kinetics Gateway V2 — Complete Read-Only Backend

This backend is prepared for FRDM i.MX93 physical validation with a three-level BAU BMS, four rack/BCU assets, complete power/environment extraction and a PCS driver that is ready for final vendor decoding overrides.

## Implemented

- Complete multi-rate BMS extraction
- BAU, four racks and all BMS-exposed environment assets
- Full cell/temperature arrays
- All 230 PCS registers in raw mode
- Persistent Modbus TCP connections
- Shared-switch and separate-interface networking profiles
- Mock/hardware/mixed/read-only modes
- FastAPI REST
- Compact snapshot plus delta WebSocket
- JWT internal/customer roles
- Alarms and alarm history
- Compressed SQLite historian
- 25 GiB quota and retention
- SD mount validation and fallback
- Rotating logs and CSV exports
- Systemd installation
- Hardware validation tools
- **16 automated tests passing**

## Current shared-switch topology

```text
FRDM eth1 -> switch -> BMS + PCS
FRDM eth0 -> PC / local Flutter
FRDM mlan0 -> Wi-Fi + existing Cloudflare tunnel
```

The default field profile supports BMS and PCS on different IP subnets over the same switch by assigning both `10.30.4.2/24` and `192.168.1.2/24` to eth1.

## Run mock mode

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export KINETICS_CONFIG=configs/kinetics_mock.json
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Mock credentials:

```text
internal / Internal@123
customer / Customer@123
```

## Install on FRDM i.MX93

```bash
sudo sh backend/deployment/install_on_imx93.sh
```

Then update production credentials:

```text
/etc/kinetics-gateway/kinetics-gateway.env
```

Review hardware endpoints:

```text
/etc/kinetics-gateway/config.json
```

Review network addresses:

```text
/etc/kinetics-gateway/network.conf
```

## Tomorrow’s read-only commands

Check interfaces:

```bash
ip -br address
ip route
```

Probe candidate BAU endpoints:

```bash
cd /opt/kinetics-gateway/backend
/opt/kinetics-gateway/venv/bin/python tools/modbus_probe.py \
  --host 10.30.4.13 \
  --source-ip 10.30.4.2 \
  --ports 503 504 505 506 507 \
  --unit-ids 1 2 3 4 5 127 \
  --address 0x0000 --count 1 --functions 3 4
```

Run complete extraction validation:

```bash
cd /opt/kinetics-gateway/backend
KINETICS_CONFIG=/etc/kinetics-gateway/config.json \
/opt/kinetics-gateway/venv/bin/python tools/hardware_read_validation.py \
  --config /etc/kinetics-gateway/config.json \
  --output /mnt/ems-logs/kinetics-gateway/hardware_read_validation.json
```

Service status:

```bash
systemctl status kinetics-network.service kinetics-gateway.service cloudflared.service
journalctl -u kinetics-gateway.service -f
```

## Main API endpoints

```text
POST /api/auth/login
GET  /api/health
GET  /api/assets
GET  /api/telemetry/snapshot
GET  /api/telemetry/compact
GET  /api/bms/bank
GET  /api/bms/racks
GET  /api/bms/racks/{rack_id}/details
GET  /api/bms/environment
GET  /api/pcs
GET  /api/alarms
GET  /api/historian/{asset_id}
GET  /api/storage/status
GET  /api/diagnostics/polling
GET  /api/diagnostics/data-rate
WS   /ws/telemetry?token=...&mode=delta
WS   /ws/telemetry?token=...&mode=full
WS   /ws/alarms?token=...
```

Use delta mode for normal Flutter/cloud operation. Full mode is retained only for engineering/debug compatibility.

## Documentation

- `IMPLEMENTATION_STATUS.md`
- `DATA_RATE_AND_STORAGE_ANALYSIS.md`

All hardware writes remain disabled in the supplied production template.

## BMS-only hardware test

A ready profile is included at `backend/configs/kinetics_hardware_bms_only.json`.
It keeps the full multi-rate BAU/rack/environment extraction enabled and disables PCS polling entirely.

```bash
cp /opt/kinetics-gateway/backend/configs/kinetics_hardware_bms_only.json \
  /etc/kinetics-gateway/config.json
systemctl restart kinetics-gateway.service
```

To re-enable PCS later, set `"pcs": {"enabled": true, ...}` in the active config and restart the service.
