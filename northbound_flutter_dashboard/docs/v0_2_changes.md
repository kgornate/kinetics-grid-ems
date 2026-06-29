# NorthBound Flutter Dashboard v0.2 Changes

v0.2 keeps the app read-only and focused on local/debug dashboard use over direct Ethernet `eth0`, while still allowing optional Cloudflare remote access from the settings page.

## Main changes

1. Dynamic asset cards are still generated from `GET /api/assets`.
2. Asset cards now show 3-4 key signal values from `GET /api/telemetry/key-signals`.
3. The dashboard now parses key-signal payloads flexibly, supporting both map and list based API shapes.
4. Asset card layout now shows:
   - asset display name
   - asset id and type
   - online/offline status
   - important key-signal preview values
   - signal count
   - bad signal count
   - last update time
5. The dashboard top summary now includes:
   - gateway health
   - read-only mode
   - WebSocket frame count
   - alarm count
   - active connection path: local eth0 or Cloudflare
6. `/api/assets` parsing is more robust. It supports `assets` as a list or as a map keyed by asset ID.
7. The app remains fully read-only. No POST, command, control, write, start, stop, charge, or discharge APIs are called.

## Default local connection

```text
API: http://192.168.10.2:8000
WS:  ws://192.168.10.2:8000/ws/telemetry
```

This is used when the PC is directly connected to i.MX93 `eth0`.

## Optional remote connection

```text
API: https://ems-api.unityess.cloud
WS:  wss://ems-api.unityess.cloud/ws/telemetry
```

This is used only when the Flutter app is running remotely and must reach the gateway through Cloudflare Tunnel.

## Dynamic asset rendering logic

```text
Flutter starts
  -> GET /api/health
  -> GET /api/assets
  -> GET /api/telemetry/key-signals
  -> GET /api/alarms
  -> creates one card per returned asset
  -> injects matching asset key-signal previews into each card
```

Expected current assets:

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

If more assets are added later, the dashboard creates cards automatically as long as the gateway returns them from `GET /api/assets`.
