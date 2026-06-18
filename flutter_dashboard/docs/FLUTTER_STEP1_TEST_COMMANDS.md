# Flutter Step 1 Test Commands

Run these after copying the updated dashboard into your PC repo.

## 1. Go to Flutter dashboard

```powershell
cd C:\Users\KunalGupta\EMS_Ornte_Code_base\kinetics-grid-ems\flutter_dashboard
```

## 2. Clean generated files if needed

```powershell
flutter clean
flutter pub get
```

## 3. Static analysis

```powershell
flutter analyze
```

## 4. Run desktop dashboard

```powershell
flutter run -d windows
```

## 5. Confirm existing behavior

Check:

```text
UDP telemetry still updates dashboard
TCP commands still work
PCS screen still works
BMS screen still works
Logs screen still works
Log filters still work
```

## 6. Backend URLs to keep in mind

Current stable gateway backend exposes:

```text
Web API:  http://<gateway-ip>:8000
Log API:  http://<gateway-ip>:7000
TCP:      <gateway-ip>:6000
UDP:      local PC listens on 5005
```

The current default gateway IP remains:

```text
192.168.10.2
```

## 7. Git checks

```powershell
git status
git diff --stat
```

Commit only source files, not build artifacts.
