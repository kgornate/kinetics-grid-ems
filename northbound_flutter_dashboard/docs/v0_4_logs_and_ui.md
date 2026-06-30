# NorthBound Flutter Dashboard v0.4 - Logs, Filters, Storage, and UI Polish

v0.4 adds a Kinetics-style logging/history UI on top of the NorthBound Gateway v0.5 storage APIs. It also improves the asset-detail experience so each asset is easier to inspect during commissioning.

## Gateway APIs used

The new Logs screen uses:

```text
GET /api/logs
GET /api/logs/summary
GET /api/logs/filters
GET /api/logs/export.csv
```

The new Storage screen uses:

```text
GET /api/storage/status
GET /api/storage/health
```

The existing dashboard still uses:

```text
GET /api/health
GET /api/assets
GET /api/telemetry/key-signals
GET /api/alarms
WS  /ws/telemetry
```

## Logs UI features

The Logs screen provides filters for:

```text
severity
asset_id
event_type
source
from_time
to_time
search text
limit
order
```

It also includes:

```text
summary cards
total / warnings / errors counts
paginated log result list
payload JSON expansion per log
CSV export URL copy
```

## Storage UI features

The Storage screen shows:

```text
storage writable / blocked state
mount status
DB size
free space
retention days
snapshot interval
SQLite table row counts
raw storage JSON
```

This maps directly to the v0.5 storage-protection behavior where data should be stored under `/mnt/ems-logs` or the configured storage path instead of filling the root filesystem.

## Asset UI improvements

Asset cards now have asset-specific icons and an online/offline status color strip. The asset detail page now includes:

```text
asset hero/status section
loaded signal count
good/bad quality summary
category count
category chips
search box
raw payload viewer
```

## Read-only status

v0.4 still does not call command/control/write APIs. It remains a monitoring, debug, and commissioning dashboard.
