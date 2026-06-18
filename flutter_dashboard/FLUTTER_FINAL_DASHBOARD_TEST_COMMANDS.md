# Flutter Final Dashboard Test Commands

Run on the Windows Flutter development machine.

## 1. Replace Flutter folder

Copy/extract this package into:

```text
C:\Users\KunalGupta\EMS_Ornte_Code_base\kinetics-grid-ems\flutter_dashboard
```

## 2. Flutter checks

```powershell
cd C:\Users\KunalGupta\EMS_Ornte_Code_base\kinetics-grid-ems\flutter_dashboard

flutter clean
flutter pub get
flutter analyze
flutter test test\repository_construction_test.dart
flutter test test\dynamic_asset_widget_test.dart
flutter test test\log_filter_builder_test.dart
flutter test test\command_catalog_test.dart
flutter test test\monitoring_screen_smoke_test.dart
```

## 3. Run app

```powershell
flutter run -d windows
```

## 4. Manual checks

Use the i.MX93 gateway IP that the Flutter app can reach. Common Ethernet IP:

```text
192.168.10.2
```

Verify old behavior:

```text
UDP telemetry updates
PCS telemetry grid works
BMS telemetry grid works
Chiller telemetry grid works
Command panel still sends commands
PCS screen opens
BMS screen opens
Logs screen works with filters
```

Verify new pages from the dashboard AppBar:

```text
Operator -> opens operator telemetry dashboard
Assets   -> opens dynamic asset navigation
Health   -> opens gateway + asset health dashboard
Storage  -> opens storage health page
Logs     -> opens existing logs screen
```

## 5. Backend API prerequisites

The stable EMS gateway backend should be running with:

```bash
python3 -u main.py --config-file configs/actual_network_assets.json --no-chiller
```

Backend APIs expected:

```text
/api/assets
/api/telemetry/operator
/api/health
/api/health/assets
/api/diagnostics
/api/storage/health?asset_id=pcs_1
```
