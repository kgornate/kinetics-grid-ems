# Kinetics Gateway Flutter Dashboard V2.6

Windows/Android monitoring and internal commissioning application for the Kinetics Gateway backend.

## Current scope

- Direct Ethernet, Wi-Fi or Cloudflare API connection by changing only the base URL.
- JWT login with internal and customer roles.
- REST bootstrap plus delta WebSocket telemetry and reconnect.
- BAU/bank, Rack 1-4, environment assets, PCS 1-4, alarms, historian and diagnostics.
- Five-minute timeouts for full hardware extraction where needed.
- Internal-only BESS Control screen for the field-validated Rack 1 ↔ PCS 1 sequence.
- Customer users remain read-only.

## BESS Control screen

Backend requirement: Kinetics Gateway V2.5.0 or newer.

The internal Control screen provides:

- live BMS/PCS readiness and safety gates
- automatic charge/discharge startup with target power and configurable ramp
- step-by-step commissioning with **Execute next step**
- direct set-power command after gateway readiness verification
- zero-power command
- complete safe shutdown
- automatic-sequence abort
- live progress stepper and latest raw gateway response

Automatic mode is shown but disabled until the backend reports `full_automatic_sequence_allowed = true`.

## Gateway URLs

- Direct PC-to-FRDM Ethernet: `http://192.168.10.2:8000`
- Wi-Fi: `http://<FRDM_WIFI_IP>:8000`
- Cloudflare: `https://<YOUR_KINETICS_HOSTNAME>`

## Temporary commissioning accounts

- Internal: `internal` / `Internal@123`
- Customer: `customer` / `Customer@123`

Change temporary passwords after commissioning.

## Build and run on Windows

```powershell
cd C:\path\to\kinetics_flutter_dashboard_v2
flutter clean
flutter pub get
flutter analyze
flutter test
flutter run -d windows
```

Build a release bundle:

```powershell
flutter build windows --release
```

Output:

```text
build\windows\x64\runner\Release\
```

## Control validation checklist

1. Deploy Gateway V2.5.0 and verify `/api/control-sequence/capabilities`.
2. Sign in as `internal`.
3. Open **Control**.
4. Confirm write gates, pair mapping, E-stop, faults and communication are healthy.
5. Use **Execute next step** for commissioning, or enable the independently gated automatic sequence after field approval.
6. Keep the physical E-stop accessible during energized tests.
7. Use **Zero power** before changing direction.
8. Use **Safe shutdown** to stop PCS and open/disable the BMS rack.

## Platform note

The networking client uses `dart:io`; this source targets Windows desktop and Android. Flutter Web is not enabled for live API use.
