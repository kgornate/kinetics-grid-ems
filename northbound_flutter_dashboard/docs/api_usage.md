# API Usage From Flutter

Default local base URL:

```text
http://192.168.10.2:8000
```

Default local WebSocket:

```text
ws://192.168.10.2:8000/ws/telemetry
```

Remote Cloudflare base URL:

```text
https://ems-api.unityess.cloud
```

Remote Cloudflare WebSocket:

```text
wss://ems-api.unityess.cloud/ws/telemetry
```

## Frontend startup sequence

1. Call `GET /api/health`.
2. Call `GET /api/assets`.
3. Call `GET /api/telemetry/key-signals`.
4. Connect WebSocket `/ws/telemetry`.
5. For asset detail pages, call `GET /api/assets/{asset_id}/telemetry`.
6. For alarm screen, call `GET /api/alarms`.

## Why WebSocket and REST both exist

REST is stable and easy for one-time page loads, manual refresh, debug, and fallback.
WebSocket is useful for live dashboard updates without polling.

## v0.2 APIs Used for Rich Dynamic Cards

The main dashboard uses four REST calls during refresh:

```text
GET /api/health
GET /api/assets
GET /api/telemetry/key-signals
GET /api/alarms
```

`GET /api/assets` controls which cards appear. `GET /api/telemetry/key-signals` controls what important values are shown inside each card.

When an asset card is clicked, the app calls:

```text
GET /api/assets/{asset_id}/telemetry
```

The app still uses WebSocket for live telemetry reception:

```text
WS /ws/telemetry
```

The app does not call POST command APIs. It is read-only.
