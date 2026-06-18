# Flutter Upgrade Step 2 - Backend-Aligned Models

## Goal

Step 2 adds typed Flutter models aligned with the stable EMS gateway backend APIs. This is an additive change: existing screens and services continue working, while future screens/repositories can use typed models instead of raw `Map<String, dynamic>` everywhere.

## Added models

```text
lib/models/asset_model.dart
lib/models/telemetry_models.dart
lib/models/health_models.dart
lib/models/diagnostics_models.dart
lib/models/command_models.dart
lib/models/log_filter_model.dart
lib/models/gateway_models.dart
lib/models/models.dart
```

## Updated models

```text
lib/models/log_models.dart
```

`LogApiResponse` now also exposes:

```text
offset
filters
```

This matches the backend log query/filter abstraction.

## Updated services

```text
lib/services/gateway_api_service.dart
lib/services/log_api_service.dart
```

Added typed helper methods while preserving existing raw JSON methods.

## Backend API alignment

The new models map to these stable backend APIs:

```text
GET /api/assets
GET /api/assets/{asset_id}
GET /api/telemetry/operator
GET /api/assets/{asset_id}/telemetry/operator
GET /api/health
GET /api/health/assets
GET /api/health/assets/{asset_id}
GET /api/diagnostics
GET /api/diagnostics/assets/{asset_id}
GET /api/logs/telemetry
GET /api/logs/events
GET /api/logs/errors
```

## Existing UI behavior

No dashboard UI refactor is done in this step.

Existing screens should continue using the same services and flows:

```text
UDP telemetry
TCP commands
PCS screen
BMS screen
Logs screen
Fixed dashboard layout
```

## Why this helps

This prepares the Flutter app for the next steps:

```text
repository layer
dynamic asset cards
health cards
operator telemetry grid
clean log filters
command catalog
```

The main benefit is that future UI code can deal with typed models such as:

```text
AssetModel
TelemetryEnvelope
AssetHealthModel
DiagnosticsResponse
LogFilterModel
GatewayCommandRequest
```

instead of parsing backend JSON directly in widgets.
