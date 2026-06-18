# Flutter Step 2 Test Commands

Run from the Flutter project root after copying this package to your PC.

## 1. Clean and fetch dependencies

```powershell
cd C:\Users\KunalGupta\EMS_Ornte_Code_base\kinetics-grid-ems\flutter_dashboard
flutter clean
flutter pub get
```

## 2. Static analysis

```powershell
flutter analyze
```

## 3. Run desktop app

```powershell
flutter run -d windows
```

## 4. Manual validation

Verify existing behavior still works:

```text
Dashboard opens
UDP telemetry updates
TCP command buttons still work
PCS screen loads
BMS screen loads
Logs screen loads
Existing log filters still work
```

## 5. Backend model readiness check

The new models are not yet deeply wired into UI screens. They are introduced so the next step can add repositories and dynamic UI safely.

Files to inspect:

```text
lib/models/models.dart
lib/models/asset_model.dart
lib/models/telemetry_models.dart
lib/models/health_models.dart
lib/models/diagnostics_models.dart
lib/models/log_filter_model.dart
lib/services/gateway_api_service.dart
lib/services/log_api_service.dart
```
