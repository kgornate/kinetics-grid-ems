# Flutter Upgrade Step 1: Core API/Config Foundation

## Goal

This update adds a modular foundation under `lib/core/` while keeping existing screens and UI behavior unchanged.

The app can still use the current fixed dashboard screens, TCP command flow, UDP telemetry flow, and log screen. The new core layer prepares the Flutter dashboard for the latest stable EMS gateway backend APIs.

## Added folders

```text
lib/core/
  api/
  config/
  network/
  utils/
```

## Added files

```text
lib/core/api/api_client.dart
lib/core/api/api_exception.dart
lib/core/api/endpoint_paths.dart
lib/core/api/query_utils.dart
lib/core/api/api.dart

lib/core/config/app_environment.dart
lib/core/config/network_config.dart
lib/core/config/config.dart

lib/core/network/tcp_socket_client.dart
lib/core/network/udp_json_listener.dart
lib/core/network/network.dart

lib/core/utils/json_utils.dart
lib/core/utils/utils.dart
```

## Updated existing files

```text
lib/config/app_config.dart
lib/services/log_api_service.dart
lib/services/tcp_command_service.dart
lib/services/udp_telemetry_service.dart
```

## What changed internally

### 1. Central network configuration

`NetworkConfig` centralizes REST, TCP, UDP, and log API connection settings.

This prepares the app to switch between:

```text
hardware eth0
Wi-Fi REST API
localhost development
future settings screen
```

without hardcoding IPs across UI files.

### 2. Common REST client

`ApiClient` centralizes:

```text
HTTP GET
JSON parsing
timeout handling
socket errors
HTTP status errors
```

`LogApiService` now uses this common client.

### 3. Endpoint constants

`EndpointPaths` centralizes stable backend URLs such as:

```text
/api/assets
/api/telemetry/operator
/api/health
/api/diagnostics
/api/logs/telemetry
/api/storage/health
```

This avoids scattering endpoint strings in many widgets/services.

### 4. Reusable TCP client

`TcpSocketClient` centralizes line-oriented TCP JSON request/response logic.

`TcpCommandService` now uses it internally.

### 5. Reusable UDP JSON listener

`UdpJsonListener` centralizes raw UDP JSON reception.

`UdpTelemetryService` still exposes existing typed streams:

```text
telemetryStream
pcsTelemetryStream
bmsTelemetryStream
rawPacketStream
```

### 6. Safe JSON utilities

`JsonUtils` provides shared helpers for safe map/list/int/double/bool/string conversion.

`UdpTelemetryService` now uses `JsonUtils.asMap()` instead of duplicating map parsing logic.

### 7. Additive gateway REST service

`GatewayApiService` was added for stable backend Web API endpoints:

```text
fetchAssets()
fetchLatestTelemetry(operatorView: true)
fetchAssetTelemetry(...)
fetchHealth()
fetchAssetsHealth()
fetchDiagnostics()
```

Existing screens do not need to switch to it immediately, but future dashboard/health/operator UI work should use it.

## What did not change

Existing UI screens are not refactored yet:

```text
dashboard_screen.dart
pcs_screen.dart
bms_screen.dart
logs_screen.dart
```

Existing visible behavior should remain the same.

## Next Flutter steps

Recommended next stages:

```text
1. Backend-aligned models: AssetModel, HealthModel, DiagnosticsModel, OperatorTelemetryModel
2. Repository layer: AssetRepository, HealthRepository, TelemetryRepository, CommandRepository, LogRepository
3. Break large screens into controllers/widgets
4. Use /api/assets dynamically
5. Add health cards and operator telemetry views
```
