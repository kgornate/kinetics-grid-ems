# Kinetics Gateway V2 — Read-Only Extraction Status

## Current status

The gateway backend is ready for physical BMS validation in read-only mode.

Automated result: **17 tests passed**.

## Complete extraction coverage

- BAU/bank active points: 155
- Rack/BCU active points: 371 per rack
- Configured racks: 4
- Power/environment active points: 131
- PCS points: 230 raw/override-ready registers
- Complete cell and temperature arrays are included through the bulk polling class.

The complete merged cache therefore contains:

```text
1 BAU + 4 rack/BCU assets + 7 environment assets + 1 PCS = 13 logical assets
```

## Implemented scheduler

Independent background tasks:

```text
BMS fast    1 second
BMS normal  5 seconds
BMS slow   60 seconds
BMS bulk   30 seconds
PCS         5 seconds
```

All groups merge into one complete latest snapshot. WebSocket clients receive one complete compact snapshot and then group-specific deltas.

## Current network topology

Prepared current profile:

```text
eth1 -> Ethernet switch -> BAU/BMS and PCS
eth0 -> engineering PC / local Flutter
mlan0 -> Wi-Fi / internet / existing Cloudflare tunnel
```

The shared-switch profile assigns two field-side addresses to eth1 so BMS and PCS can remain on different IP subnets:

```text
eth1: 10.30.4.2/24
eth1: 192.168.1.2/24
eth0: 192.168.10.2/24
```

Initial endpoints:

```text
BMS: 10.30.4.13, source 10.30.4.2, port 503
PCS: 192.168.1.200, source 192.168.1.2, port 502
```

All IPs, ports, Unit IDs and source IPs are configurable.

A separate-interface profile is also included. With only two native Ethernet ports, dedicating one to BMS and one to PCS means the engineering PC must use Wi-Fi or an additional USB Ethernet adapter.

## Remote/local data delivery

- FastAPI listens on `0.0.0.0:8000`.
- PC access over eth0: `http://192.168.10.2:8000`.
- Wi-Fi access uses the mlan0 address.
- Existing Cloudflare tunnel can continue forwarding to `http://127.0.0.1:8000`.
- REST provides snapshots/history/configuration.
- WebSocket provides live telemetry and alarms.

## Storage

- Preferred path: `/mnt/ems-logs/kinetics-gateway`
- SQLite database with WAL mode
- Compressed compact telemetry BLOBs
- Complete plant sample every 5 seconds
- 25 GiB application quota
- 90% quota high-watermark
- Age and quota retention
- Rotating runtime log
- CSV export

Estimated mock-profile storage is approximately 0.266 GiB/day, giving approximately 84.6 days before the 90% quota high-watermark.

## Security

- JWT authentication
- Internal role
- Customer read-only role
- Passwords and JWT secret through environment variables
- Read-only hardware mode forces both BMS and PCS writes off
- Write driver foundation remains present for later approved control implementation
- Command audit trail remains available

## Tomorrow’s validation

1. Apply the shared-switch network profile.
2. Confirm routes and ping BMS/PCS.
3. Probe BAU ports and Unit IDs.
4. Run the complete hardware read validation tool.
5. Check point quality, block errors and polling duration.
6. Compare key values against BAU/PCS HMI.
7. Leave all writes disabled.
