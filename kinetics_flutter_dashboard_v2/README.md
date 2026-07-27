# Kinetics Gateway Flutter Dashboard V2

Read-only commissioning and monitoring application for the Kinetics Gateway V2 backend.

## Current scope

- Connect through direct Ethernet, Wi-Fi, or Cloudflare by changing only the API base URL.
- JWT login for `internal` and `customer` roles.
- REST bootstrap and health checks.
- Delta WebSocket telemetry with automatic reconnect.
- BAU/bank telemetry covering every point returned by the gateway.
- Four rack/BCU assets and complete rack detail reads, including bulk arrays.
- HVAC, liquid cooling, energy meter, dehumidifiers, safety/fire I/O, and other environment assets.
- Active alarms and alarm history.
- SQLite historian browser.
- Scheduler, storage, and bandwidth diagnostics.
- Internal-user mock scenario selection when the gateway is in mock or mixed mode.
- One-button complete BMS extraction for commissioning.
- PCS screen support is dynamic; it displays disabled status now and automatically displays data when PCS is enabled.
- No BMS or PCS write controls are exposed in this read-only application.

## Gateway URLs

- Direct PC-to-FRDM Ethernet: `http://192.168.10.2:8000`
- Wi-Fi: `http://<FRDM_WIFI_IP>:8000`
- Cloudflare: `https://<YOUR_KINETICS_HOSTNAME>`

All three routes expose the same REST and WebSocket API contract.

## Temporary commissioning accounts

- Internal: `internal` / `Internal@123`
- Customer: `customer` / `Customer@123`

The passwords come from the gateway environment file and must be changed after commissioning.

## Build and run on Windows

```powershell
cd C:\path\to\kinetics_flutter_dashboard_v2
flutter clean
flutter pub get
flutter test
flutter run -d windows
```

Build a release executable:

```powershell
flutter build windows --release
```

The release bundle will be under:

```text
build\windows\x64\runner\Release\
```

## Tomorrow's BMS test flow

1. Install and run the BMS-only gateway backend.
2. Connect the PC to FRDM `eth0` and set the PC IP to `192.168.10.10/24`.
3. Confirm `ping 192.168.10.2` and TCP port 8000.
4. Run this Flutter app and connect to `http://192.168.10.2:8000`.
5. Sign in as `internal`.
6. Confirm REST and Live indicators are green.
7. Open Diagnostics and select **Run total extraction**.
8. Check BAU, Rack 1-4, Environment, Alarms, Historian, Polling, and Storage screens.
9. Compare key values against the BAU/HMI.

## Platform note

The networking client uses `dart:io`, so this source is intended for Windows desktop and Android. Flutter Web is not enabled for live API use in this version.

## V2.3 stability update

The BAU, environment asset, and generic telemetry "All points" expansion panels now have explicit Material/Card ancestors. This fixes the intermittent red-screen error that could require closing and reopening a view. See `PATCH_NOTES_V2_3.md`.


## V2.5 PCS topology

The PCS area supports four physical PCS units connected to one RS485 bus through Modbus RTU slave IDs 1–4. The gateway must publish the devices in `pcs_devices`; the legacy single `pcs` field remains supported.
