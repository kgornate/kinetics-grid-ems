# NorthBound Flutter Dashboard v0.6 - Operator Asset Field Strategy

v0.6 turns the previous logs UI into a more correct operator-facing data view.

## Core strategy

The app now separates three different concepts:

```text
Live Asset Fields  = current decoded values from /api/assets/{asset_id}/telemetry
Historian          = stored telemetry values from /api/storage/points
Gateway Events     = technical event/audit records from /api/logs
```

The operator should normally start from **Live Asset Fields** and **Historian**. Gateway Events are kept as a maintenance/developer tab and API access events remain hidden by default.

## Asset-specific grouping

The Flutter app now contains an asset field strategy layer:

```text
lib/utils/asset_field_strategy.dart
```

It defines how different NorthBound assets should be organized:

| Asset | Main groups |
| --- | --- |
| EMS System | modes, system status, SOC/limits, power/commands, safety |
| BMS | SOC/SOH, voltage, current/power, temperature, insulation, contactors/precharge, communication, energy, faults |
| PCS | status/mode, power, AC side, DC side, voltage, current, temperature, insulation, energy, faults |
| Utility Meter | voltage, current, power/PF, energy, frequency/temperature, alarms |
| Fire Protection | communication/status, temperature, fire/gas/IR, outputs/feedback, faults/alarms |
| Liquid Cooling | mode/status, temperature/setpoints, pressure/flow, compressor/fan, power supply, communication, faults/alarms |
| Dehumidifier | temperature, humidity, mode/status, alarms |
| I/O Module | communication/status, digital inputs, digital outputs, safety/faults |
| Remote Status | remote mode/limits, schedule power, schedule time, status/fault reset |

## Live Asset Fields tab

For the selected asset, v0.6 shows:

- Asset purpose card
- Important operator values
- Good/bad quality counts
- Fault/alarm field count
- Asset-specific grouping summary
- Filters by category, quality, fault/alarm-only, and free-text search
- Operator table columns: field, value, unit, category, quality, address, updated, description/enum
- Click a field to jump to Historian for that signal

## Historian tab

Historian reads:

```text
GET /api/storage/points?asset_id=<asset>&signal_name=<signal>&limit=<rows>
```

It is intended for stored asset values, not API-access logs. The gateway v0.5 may store only key signals depending on `store_mode`.

## Gateway Events tab

Gateway Events reads:

```text
GET /api/logs
GET /api/logs/summary
GET /api/logs/filters
GET /api/logs/export.csv
```

This tab is for maintenance/debug audit. API access rows such as `GET /api/assets -> 200` are hidden by default.
