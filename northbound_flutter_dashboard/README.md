# NorthBound Flutter Dashboard

**Version:** 0.3.0

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
