# NorthBound Flutter Dashboard

**Version:** 0.8.0

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

## v0.4.1 quick fix

v0.4.1 fixes a compatibility issue with NorthBound Gateway v0.5 where `/api/assets` returns the asset catalog under `items` instead of `assets`. The dashboard now supports both response shapes, so asset cards should render correctly again.

Fixed client parsing for:

```text
GET /api/assets      -> supports assets/items/data
GET /api/alarms      -> supports alarms/items/active_alarms
```

No gateway-side change is required for this fix.


## v0.5 operator data and logs redesign

v0.5 changes the logging strategy. The old logs screen was too developer-audit focused because `/api/logs` contains many API access records. The new `Asset Data & Logs` screen separates operator asset data from technical gateway events.

Tabs:

```text
Asset Fields  -> live asset telemetry table with asset/category/search filters
History       -> stored signal history from /api/storage/points
Gateway Events -> technical gateway event logs, with API access hidden by default
```

Asset detail pages now show values as metric cards and also provide a proper table view. Storage page now shows disk/database numbers in MB/GB and table layout.

More details: `docs/v0_5_operator_data_logs_redesign.md`.

## v0.6 operator asset-field redesign

v0.6 makes the logging/operator view match the real NorthBound EMS data model:

```text
Live Asset Fields  -> current decoded asset values
Historian          -> stored asset values over time
Gateway Events     -> maintenance/developer event logs
```

The app now groups asset fields using asset-specific strategy profiles for EMS System, BMS, PCS, Utility Meter, Fire Protection, Liquid Cooling, Dehumidifier, I/O Module, and Remote Status.

Main improvements:

- Logs screen is now an operator-first **Asset Data & Logs** screen.
- Live Asset Fields has asset selector, category filter, quality filter, fault/alarm-only toggle, and search.
- Asset detail pages show asset-specific purpose, important values, fault/alarm attention panel, grouped operator sections, card view, and table view.
- Historian tab reads stored asset values using `/api/storage/points`.
- Gateway Events remain available but API access noise is hidden by default.
- Storage page shows free space and DB size in MB/GB formatted values.

More details: `docs/v0_6_operator_asset_field_strategy.md`.

## v0.7 Historian Table Redesign

v0.7 improves the Historian tab so it works like an operator data table instead of a single-signal point viewer.

Historian now uses:

```text
GET /api/storage/snapshots?asset_id=<asset_id>&limit=<rows>
```

and renders historical rows as a wide table:

```text
Timestamp UTC | Selected Field 1 | Selected Field 2 | Selected Field 3 | ...
```

The columns are chosen from the same decoded asset fields used by Live Asset Fields and Asset Details. Filters are now based on asset data categories and fields:

- Asset selector
- Category filter
- Quality filter
- Fault/alarm field toggle
- Field search
- Row limit
- Select priority columns
- Select all visible columns
- Clear columns

This makes the historian match the operator workflow:

```text
select asset -> filter its fields -> select columns -> load historical rows
```

Gateway event logs remain separate under Gateway Events and are not treated as the main operator historian.

## v0.8 network timeout update

v0.8 adds profile-based HTTP timeouts because large asset payloads, especially BMS telemetry, can take much longer through Cloudflare/hotspot than local eth0.

```text
Local eth0 timeout: 5 seconds
Cloudflare timeout: 30 seconds
```

The same active profile is now used everywhere: dashboard, asset cards, asset detail pages, logs, historian, storage status, alarms, and WebSocket.

The Flutter app uses only the WebSocket endpoint:

```text
/ws/telemetry
```

It does not call the old SSE endpoint:

```text
/api/stream/telemetry
```

Details: `docs/v0_8_network_timeouts.md`.
