# Flutter Step 3 Test Commands

Run from the Flutter dashboard folder on Windows PC.

## 1. Clean and fetch packages

```powershell
cd C:\Users\KunalGupta\EMS_Ornte_Code_base\kinetics-grid-ems\flutter_dashboard
flutter clean
flutter pub get
```

## 2. Analyze

```powershell
flutter analyze
```

## 3. Run repository construction test

```powershell
flutter test test\repository_construction_test.dart
```

## 4. Run the desktop dashboard

```powershell
flutter run -d windows
```

## 5. Manual checks

Verify existing behavior is unchanged:

```text
Dashboard opens
UDP telemetry still updates
TCP commands still work
PCS screen works
BMS screen works
Logs screen works
Log filters still work
```

## 6. Future repository smoke-test usage

After screens begin using repositories, the main bundle can be constructed with:

```dart
final repositories = GatewayRepositoryBundle.forGateway('192.168.10.2');
```

Then use:

```dart
repositories.assets.fetchAssetList();
repositories.telemetry.fetchOperatorTelemetry();
repositories.health.fetchAssetsHealth();
repositories.logs.fetchTelemetryLogs(filter);
repositories.commands.readStatus();
```
