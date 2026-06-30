# Run Commands

## Replace/update project

Unzip this package over your existing `northbound_flutter_dashboard` folder or copy the `lib/`, `pubspec.yaml`, and `docs/` contents into the existing project.

If platform folders are missing, run:

```powershell
flutter create --platforms=windows,web .
```

## Windows desktop

```powershell
cd C:\Users\KunalGupta\EMS_Ornte_Code_base\kinetics-grid-ems\northbound_flutter_dashboard
$env:Path = "C:\Users\KunalGupta\develop\flutter\bin;" + $env:Path
flutter pub get
flutter run -d windows
```

## Browser

```powershell
flutter run -d chrome
```

## WebSocket verification outside Flutter

```powershell
py -m pip install websockets
```

```powershell
@'
import asyncio
import websockets

async def main():
    url = "ws://192.168.10.2:8000/ws/telemetry"
    print("Connecting:", url)
    async with websockets.connect(url) as ws:
        for i in range(5):
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            print("FRAME", i + 1, msg[:500])

asyncio.run(main())
'@ | py -
```
