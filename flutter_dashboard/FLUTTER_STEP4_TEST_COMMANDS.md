# Flutter Step 4 Test Commands

Run these from the Flutter dashboard folder on the Windows PC.

## 1. Clean and install dependencies

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

## 4. Run Windows app

```powershell
flutter run -d windows
```

## 5. Functional checks

Verify:

```text
Dashboard opens normally
UDP telemetry updates chiller/PCS/BMS cards
Gateway IP field still works
Start/Stop UDP button still works
Logs button opens logs screen
PCS detail screen opens
BMS detail screen opens
TCP commands still work
Last command result card still renders
Raw UDP packet expansion still renders
Logs table still loads telemetry/events/errors
Log filters still work
```

## 6. Backend URLs to test with stable gateway

Use the backend gateway IPs currently configured in the app:

```text
REST/Web API: http://192.168.88.16:8000
TCP command: 192.168.10.2:6000
Log API: http://192.168.10.2:7000
UDP telemetry port: 5005
```
