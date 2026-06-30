# Run Commands

## Windows desktop

```powershell
cd C:\Users\KunalGupta\EMS_Ornte_Code_base\kinetics-grid-ems\northbound_flutter_dashboard
$env:Path = "C:\Users\KunalGupta\develop\flutter\bin;" + $env:Path
flutter pub get
flutter run -d windows
```

## Generate missing platform folders

```powershell
flutter create --platforms=windows,web .
flutter pub get
flutter run -d windows
```

## Local eth0 profile

```text
API: http://192.168.10.2:8000
WS:  ws://192.168.10.2:8000/ws/telemetry
```

## Cloudflare profile

```text
API: https://ems-api.unityess.cloud
WS:  wss://ems-api.unityess.cloud/ws/telemetry
```

## Test logs API from PC

```powershell
curl "http://192.168.10.2:8000/api/logs/summary"
curl "http://192.168.10.2:8000/api/logs/filters"
curl "http://192.168.10.2:8000/api/logs?limit=20"
curl "http://192.168.10.2:8000/api/storage/status"
```
