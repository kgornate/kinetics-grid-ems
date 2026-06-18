# Flutter Upgrade Step 3: Repository Layer

## Goal

This step adds a repository layer between UI/screens and low-level services.

The existing UI is not refactored yet. Current UDP telemetry, TCP commands, PCS/BMS screens, dashboard screen, and logs screen should continue working as before.

## New folder

```text
lib/repositories/
```

## New files

```text
lib/repositories/repository_exception.dart
lib/repositories/gateway_repository.dart
lib/repositories/asset_repository.dart
lib/repositories/telemetry_repository.dart
lib/repositories/health_repository.dart
lib/repositories/diagnostics_repository.dart
lib/repositories/log_repository.dart
lib/repositories/command_repository.dart
lib/repositories/gateway_repository_bundle.dart
lib/repositories/repositories.dart
```

## What repositories do

```text
GatewayRepository      -> gateway status and health APIs
AssetRepository        -> /api/assets and /api/assets/{asset_id}
TelemetryRepository    -> /api/telemetry/operator and asset telemetry APIs
HealthRepository       -> /api/health and /api/health/assets APIs
DiagnosticsRepository  -> /api/diagnostics APIs
LogRepository          -> log API, storage health, filtered logs
CommandRepository      -> TCP command boundary
```

## Why this helps

Before this step, future UI refactors would need to call services directly.

After this step, screens can use repositories:

```dart
final repositories = GatewayRepositoryBundle.forGateway('192.168.10.2');
final assets = await repositories.assets.fetchAssetList();
final health = await repositories.health.fetchAssetsHealth();
final telemetry = await repositories.telemetry.fetchOperatorTelemetry();
```

This makes future screen refactors cleaner and safer.

## Existing behavior preserved

The following current flows are not changed in this step:

```text
UDP telemetry listener
TCP command service
Dashboard screen
PCS screen
BMS screen
Logs screen
Existing log filters
```

## Small service enhancement

`TcpCommandService.sendCommand()` now accepts optional:

```text
requestId
params
```

Existing callers continue working because these are optional. This allows the new `CommandRepository` to send typed command requests later without changing UI code.

## Next recommended step

Step 4 should start breaking large screens/controllers gradually, beginning with the dashboard screen and health/asset widgets.
