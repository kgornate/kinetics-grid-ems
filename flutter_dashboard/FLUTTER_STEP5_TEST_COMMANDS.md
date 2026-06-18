# Flutter Step 5 Test Commands

Run from the Flutter dashboard folder on Windows:

```powershell
cd C:\Users\KunalGupta\EMS_Ornte_Code_base\kinetics-grid-ems\flutter_dashboard
```

## 1. Clean and fetch packages

```powershell
flutter clean
flutter pub get
```

## 2. Static analysis

```powershell
flutter analyze
```

## 3. Run tests

```powershell
flutter test test\repository_construction_test.dart
flutter test test\dynamic_asset_widget_test.dart
```

## 4. Run desktop app

```powershell
flutter run -d windows
```

## 5. Runtime checks

With EMS gateway running, verify:

```text
Dashboard opens without crash.
UDP telemetry still updates fixed BMS/PCS/chiller cards.
Dynamic Asset Runtime panel appears near the top.
Asset cards show pcs_1, bms_1, chiller_1 based on /api/assets.
Health chips show healthy/degraded/offline/disabled based on /api/health/assets.
Refresh button in Dynamic Asset Runtime panel works.
Existing Logs screen still opens.
Existing PCS and BMS detail screens still open.
Existing TCP command panel still works.
```

## 6. Backend API pre-check

In browser or PowerShell, confirm backend APIs work first:

```powershell
$IMX_WIFI_IP = "192.168.88.16"
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/assets" | ConvertTo-Json -Depth 40
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/health/assets" | ConvertTo-Json -Depth 40
```

If these APIs fail, the dynamic asset panel will show an error message but the old UDP dashboard should still continue working.
