# NorthBound Flutter Dashboard

**Version:** 0.4.0

Read-only Flutter dashboard for the NorthBound EMS Gateway.

## Default local connection

```text
API: http://192.168.10.2:8000
WS:  ws://192.168.10.2:8000/ws/telemetry
```

## Optional Cloudflare connection

```text
API: https://ems-api.unityess.cloud
WS:  wss://ems-api.unityess.cloud/ws/telemetry
```

## v0.3 update

v0.3 fixes WebSocket handling:

- reconnect when the URL/profile changes
- auto reconnect when the socket closes or errors
- WebSocket status chip: connecting / connected / error / disconnected
- last WebSocket error display
- manual reconnect button
- subscribe before connect
- REST polling remains active as fallback

## Run

```bash
flutter create --platforms=windows,web .
flutter pub get
flutter run -d windows
```

For browser:

```bash
flutter run -d chrome
```

The app is read-only. It does not call any command/write/control APIs.


## v0.4 Logs, Filters, Storage, and UI Polish

v0.4 adds a Kinetics-style logs/history workflow for the NorthBound EMS Gateway v0.5 storage APIs.

New screens:

```text
Logs & Filters
Storage / Historian
Enhanced Asset Detail
```

The Logs screen uses:

```text
GET /api/logs
GET /api/logs/summary
GET /api/logs/filters
GET /api/logs/export.csv
```

The Storage screen uses:

```text
GET /api/storage/status
GET /api/storage/health
```

The asset detail page now has a cleaner hero/status area, metric cards, category chips, search, and raw JSON view.

The dashboard remains read-only. It does not call Modbus write, PCS/BMS control, or command APIs.

More details: `docs/v0_4_logs_and_ui.md`.
