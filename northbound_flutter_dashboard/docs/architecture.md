# Flutter Side Architecture for NorthBound EMS Gateway

## Network mode for local testing

```text
PC Flutter Desktop
    │
    │ Ethernet direct link over eth0
    ▼
i.MX93 eth0 = 192.168.10.2
NorthBound EMS Gateway API = 0.0.0.0:8000
```

The Flutter app does not talk directly to Chinese EMS, PCS, BMS, or Modbus. It only talks to the NorthBound EMS Gateway API.

## Recommended local flow

```text
Chinese EMS / mock data
        ↓
NorthBound EMS Gateway on i.MX93
        ↓ REST + WebSocket over eth0
Flutter desktop dashboard on PC
```

## Protocols used by Flutter

| Purpose | Protocol | Endpoint |
| --- | --- | --- |
| Initial health check | HTTP GET | `/api/health` |
| Asset discovery | HTTP GET | `/api/assets` |
| Dashboard cards | HTTP GET | `/api/telemetry/key-signals` |
| Asset detail pages | HTTP GET | `/api/assets/{asset_id}/telemetry` |
| Alarms | HTTP GET | `/api/alarms` |
| Live stream | WebSocket | `/ws/telemetry` |

## Data ownership

The gateway owns polling, decoding, normalization, storage, and health. Flutter only renders the data.

## Read-only guarantee

This Flutter scaffold does not implement any POST/PUT/DELETE calls. It is read-only for commissioning and debugging.

## v0.2 Dynamic Card Architecture

The dashboard is intentionally dynamic. It does not maintain a hardcoded screen for only PCS, BMS, and chiller. It first asks the gateway for the current asset catalog, then renders whatever the gateway returns.

```text
Flutter Dashboard
  -> GET /api/assets
  -> creates AssetSummary objects
  -> GET /api/telemetry/key-signals
  -> groups key signals by asset_id
  -> creates one AssetCard per asset
  -> injects 3-4 key values into each card
```

This keeps the UI aligned with the NorthBound EMS Gateway register map. If the gateway later exposes more assets, the same dashboard can render them without changing the asset-card creation logic.

### Why local eth0 remains default

For bench testing, the Windows PC connects directly to the i.MX93 over Ethernet.

```text
Flutter PC -> eth0 cable -> http://192.168.10.2:8000
```

This path does not need internet and does not need Cloudflare.

### Why Cloudflare is still configurable

Cloudflare is only another access path to the same gateway API when the dashboard is remote.

```text
Remote Flutter/browser -> https://ems-api.unityess.cloud -> Cloudflare Tunnel -> localhost:8000 on i.MX93
```

The gateway code and Flutter UI logic remain the same; only the base URL changes.
