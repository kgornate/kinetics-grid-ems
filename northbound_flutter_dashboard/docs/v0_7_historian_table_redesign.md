# NorthBound Flutter Dashboard v0.7 - Historian Table Redesign

## Reason for the change

The previous Historian tab queried one signal at a time through `/api/storage/points`. That technically worked, but the UI did not match the way operators think about asset logs. Operators expect to select an asset and see its historical values in a table with field columns.

## New historian behavior

v0.7 uses snapshot rows from:

```text
GET /api/storage/snapshots?asset_id=<asset_id>&limit=<rows>
```

Each snapshot becomes one table row. The user selects which asset fields become table columns.

## UI filters

The Historian filters now mirror the Live Asset Fields filters:

| Filter | Purpose |
| --- | --- |
| Asset | Choose BMS, PCS, meter, cooling, fire, I/O, etc. |
| Category | Show only voltage/current/power/temperature/fault/etc. fields |
| Quality | Good / bad filter |
| Fault/alarm fields | Quickly inspect stored fault/alarm signals |
| Search | Find fields by display name, signal name, value, unit, address, or description |
| Rows | Select number of historical rows |
| Column chips | Choose fields that should appear as columns |

## Important storage note

The gateway storage mode controls how many signals are historically stored.

If gateway storage is:

```text
store_mode = key_signals
```

then the historian table will contain the key signals stored in snapshots.

If gateway storage is later changed to:

```text
store_mode = full_snapshot
```

then the same Flutter table can show all stored decoded fields historically.

## Operator split

The Logs screen now has three clear purposes:

| Tab | Purpose |
| --- | --- |
| Live Asset Fields | Current decoded asset values |
| Historian | Historical snapshot rows and selected field columns |
| Gateway Events | Maintenance/developer event logs, with API access hidden by default |
