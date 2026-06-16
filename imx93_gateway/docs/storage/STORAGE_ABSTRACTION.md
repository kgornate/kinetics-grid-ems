# Storage and Logging Abstraction

The gateway now has a service-facing storage abstraction in `core/storage/`.

## Goal

The existing CSV logging behavior is preserved, but PCS, BMS, and chiller services now use a common `StorageManager` interface instead of depending directly on the CSV logger implementation.

## New structure

```text
core/storage/
  __init__.py
  storage_manager.py
  telemetry_store.py
  event_store.py
  error_store.py
  storage_status.py
```

## Current runtime flow

```text
PCS / BMS / Chiller service
        |
        v
StorageManager
        |
        +-- TelemetryStore
        +-- EventStore
        +-- ErrorStore
        +-- StorageStatus
        |
        v
Existing CSV StorageLogger backend
```

## Compatibility

The following remain unchanged:

```text
CSV file locations
CSV headers
/api/logs/assets
/api/logs/files
/api/logs/telemetry
/api/logs/events
/api/logs/errors
/api/storage/status
```

A new additive endpoint is available:

```text
GET /api/storage/health?asset_id=pcs_1
GET /api/storage/health?asset_id=bms_1
GET /api/storage/health?asset_id=chiller_1
```

## Why this helps

This makes logging cleaner for current and future assets. Later, a different backend such as SQLite, InfluxDB, or cloud sync can be added behind `StorageManager` without changing PCS/BMS/chiller service logic or frontend APIs.

## Service migration status

These services now use `StorageManager`:

```text
services/pcs_gateway_service.py
services/chiller_gateway_service.py
services/bms_gateway_service.py
```

The CSV backend still lives in:

```text
services/storage_logger.py
```

That file remains intentionally available because it is the active CSV backend.
