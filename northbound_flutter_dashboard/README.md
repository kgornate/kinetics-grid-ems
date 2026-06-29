# NorthBound Flutter Dashboard

**Version:** 0.2.0

Local debug/commissioning dashboard for the NorthBound EMS Gateway.

The app connects to the i.MX93 over `eth0` by default:

```text
PC Ethernet: 192.168.10.1
i.MX93 eth0: 192.168.10.2
Gateway API: http://192.168.10.2:8000
WebSocket:   ws://192.168.10.2:8000/ws/telemetry
```

It can also be pointed to the Cloudflare tunnel URL:

```text
https://ems-api.unityess.cloud
wss://ems-api.unityess.cloud/ws/telemetry
```

## Run on Windows desktop

```bash
flutter pub get
flutter config --enable-windows-desktop
flutter run -d windows
```

## Run on Chrome for quick testing

```bash
flutter pub get
flutter run -d chrome
```

## Important

This Flutter app is read-only. It does not call any control/write/command APIs.

## Main APIs used

- `GET /api/health`
- `GET /api/assets`
- `GET /api/telemetry/key-signals`
- `GET /api/assets/{asset_id}/telemetry`
- `GET /api/alarms`
- `GET /api/storage/status`
- `WS /ws/telemetry`

## v0.2 dashboard behavior

v0.2 keeps the app fully read-only and improves the dynamic asset-card dashboard. The app calls `GET /api/assets` and creates one card per returned asset. It also calls `GET /api/telemetry/key-signals` and shows 3-4 important values directly inside each card.

This means the dashboard is not hardcoded for only PCS/BMS/chiller. It can render assets such as `existing_ems`, `bms_1`, `pcs_1`, `utility_meter`, `fire_protection`, `liquid_cooling`, `dehumidifier`, `io_module`, and `remote_status` automatically.

The default connection remains direct local Ethernet:

```text
http://192.168.10.2:8000
ws://192.168.10.2:8000/ws/telemetry
```

Cloudflare URL support is only for remote access when the PC is not directly connected to the gateway.

More details: `docs/v0_2_changes.md`.
