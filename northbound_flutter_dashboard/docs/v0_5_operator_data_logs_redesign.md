# NorthBound Flutter Dashboard v0.5 - Operator Data and Logs Redesign

v0.5 re-strategizes the earlier Logs & Filters UI.

## Why the v0.4 logs screen was confusing

The gateway v0.5 `/api/logs` endpoint stores `gateway_events`. Many of these are technical API-access audit events such as:

```text
GET /api/assets -> 200
GET /api/telemetry/key-signals -> 200
GET /api/storage/status -> 200
```

Those are useful for developer audit/debug, but they are not the main operator view. Operators usually want to see asset fields, values, status, alarms, and history.

## New v0.5 screen strategy

The old `Logs & Filters` screen is now redesigned as:

```text
Asset Data & Logs
  1. Asset Fields
  2. History
  3. Gateway Events
```

### 1. Asset Fields tab

Purpose: operator data inspection.

Data source:

```text
GET /api/assets
GET /api/assets/{asset_id}/telemetry
```

UI behavior:

- Asset dropdown shows actual asset display names and IDs.
- Selected asset fields are shown in a proper table.
- Columns include field, value, unit, category, quality, address, and update time.
- Search filters by field name, display name, value, unit, category, quality, or address.
- Category chips filter asset data by category.
- Clicking a field jumps to the History tab with that signal selected.

### 2. History tab

Purpose: stored telemetry point inspection.

Data source:

```text
GET /api/storage/points?asset_id=<asset>&signal_name=<signal>&limit=<rows>
```

UI behavior:

- Select asset.
- Select signal/field.
- Select row limit.
- Load historical table with timestamp, asset, signal, value, category, and quality.

Note: storage may contain only key signals depending on gateway `store_mode`.

### 3. Gateway Events tab

Purpose: developer/technical audit, warnings, errors, storage events, upload events, and API access logs.

Data source:

```text
GET /api/logs
GET /api/logs/summary
GET /api/logs/filters
GET /api/logs/export.csv
```

UI behavior:

- API access logs are hidden by default because they are noisy.
- A toggle allows showing API access logs when debugging.
- Event filters still support severity, asset, event type, source, search, time range, limit, order, and pagination.
- CSV export URL copy is retained.

## Storage screen improvements

The Storage/Historian page now displays:

- DB size in MB/GB.
- Free disk space in MB/GB.
- Disk used percentage.
- Storage details in a table.
- SQLite table counts in a table.

## Asset detail screen improvements

Each asset detail page now has:

- Hero summary card.
- Important values grid.
- Metric cards for each field.
- Table view for all fields.
- Category chips and search.

The UI remains read-only.
