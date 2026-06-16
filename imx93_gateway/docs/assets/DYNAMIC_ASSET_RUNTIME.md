# Dynamic Asset Runtime

## Purpose

The gateway can now build API asset lists and health views from the configured asset list instead of only relying on fixed hardcoded assets.

The active services are still the current stable paths:

```text
Chiller  -> Modbus RTU service
PCS      -> Modbus TCP service
BMS      -> Modbus TCP service
```

The dynamic runtime catalog adds an asset-indexed layer above those services so the API can represent both active assets and configured future assets in one consistent way.

## Added module

```text
core/assets/runtime_catalog.py
```

Main objects:

```text
RuntimeAssetCatalog
RuntimeAssetRecord
```

The catalog merges:

```text
configured assets from config
runtime status from gateway status
latest telemetry from telemetry pipeline
```

## What this enables now

```text
/api/assets becomes asset-list aware
/api/assets/{asset_id} can return configured assets
/api/health/assets includes configured assets
/api/health/assets/{asset_id} works with configured assets
/api/diagnostics includes configured assets
```

This is useful when you want the system to know about future assets before active drivers/services are fully integrated.

## Current behavior

Active runtime is still stable and compatibility-first:

```text
pcs_1     active service when enabled
bms_1     active service when enabled
chiller_1 active service when enabled
```

Additional configured assets can appear as:

```text
configured_only
configured_future
disabled
```

These modes clearly tell the frontend/backend team whether the asset is active, only configured, planned for future integration, or disabled.

## Important limitation

This update does not magically add a working driver for every configured asset. For example, an energy meter or CAN BMS can now be represented cleanly in config and APIs, but a real driver/service still has to be implemented before that asset can produce live telemetry.

## Runtime modes

```text
active_service      -> current service is running
configured_only     -> asset is configured but no runtime service is active
disabled            -> asset is configured but disabled
configured_future   -> asset uses a protocol/type that is known but not active in current runtime
```

## API behavior

Use:

```text
GET /api/assets
GET /api/assets/{asset_id}
GET /api/health/assets
GET /api/health/assets/{asset_id}
GET /api/diagnostics
GET /api/diagnostics/assets/{asset_id}
```

For active assets, telemetry endpoints remain unchanged:

```text
GET /api/assets/pcs_1/telemetry/latest
GET /api/assets/bms_1/telemetry/latest
GET /api/assets/chiller_1/telemetry/latest
```

For configured-only assets, telemetry may return no telemetry until a driver/service is implemented and registered.

## Frontend impact

No existing frontend behavior should break.

Later, when frontend is updated, it should use:

```text
GET /api/assets
```

to discover assets dynamically instead of assuming only one PCS, one BMS, and one chiller.
