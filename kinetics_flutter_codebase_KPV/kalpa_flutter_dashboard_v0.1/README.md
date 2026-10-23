# Kalpa Gateway Flutter Dashboard — categorized asset views

This desktop source project adapts the supplied Kinetics dashboard's screen architecture to the Kalpa DEBIX backend. It keeps the original Material theme, overview cards, asset tabs and categorized parameter tables, with Lineage BMS and Elecod PCS signal mappings.

## Screen structure

| Asset | Detail tabs |
| --- | --- |
| BMS rack | Overview, Electrical, Thermal, Cells, Sensors, Alarms & faults, Settings, All signals |
| PCS | Overview, DC side, AC / Grid, Thermal, Operating status, Alarms & faults, Settings, All signals |
| System BMS | Overview, Electrical, Thermal, Energy, Operating status, Alarms & faults, Settings, All signals |
| Environment | Overview, Measurements, Operating status, Alarms & faults, Settings, All signals |

The Cells tab has channel-count/range cards plus separate voltage, temperature, SOC and balance tables. Pack voltage and terminal-temperature channels belong to Sensors. Tables show readable parameter names, values, units, quality and register addresses; each category has search and local pagination. Numbered channels sort naturally (1, 2, 3 ... 10), and point details remain available by clicking a parameter/value. Unknown future signals stay accessible; reserved points remain in All signals.

Compact telemetry omits names/units/registers, so display metadata is included from the supplied Lineage V05 and Elecod V2.7.0 catalogs. The UI displays backend engineering values without applying Kinetics scaling or reinterpreting FLOAT32 data. It preserves positive Lineage current as charging. Offline/bad-quality readings show dashes; valid zero values stay zero.

Only received points are displayed. A Settings table can be empty when backend parameter readback is disabled. The read-only UI does not enable additional polling or write gates. The rack toolbar's explicit **Load complete rack data** button uses the existing rack-detail API to fetch missing bulk channels.

## Use this update

Close the old app and extract this full ZIP into a fresh folder. Open PowerShell in the inner folder containing pubspec.yaml. Do not copy just the previously patched monitoring file: categorized views also require the new detail screen and display catalog.

If preserving an existing project, merge the lib, test and tool folders from this package. No gateway-side patch is required for these UI changes.

```powershell
flutter pub get
flutter test test/kalpa_asset_navigation_test.dart
dart run tool/kalpa_category_contract_check.dart
flutter run -d windows
```

Sign in with the same customer/internal application account and gateway URL. The app uses direct REST/WebSocket communication; there is no laptop SSH tunnel requirement.

## Direct connection URLs

| Connection | App API URL |
| --- | --- |
| PC Ethernet to gateway eth0 | http://192.168.10.2:8000 |
| Same WiFi network | http://GATEWAY_WIFI_IP:8000 |
| Remote Cloudflare | https://gw3-api.unityess.cloud |

The wired PC should use 192.168.10.1/24. The WiFi preset uses the last known example 192.168.0.122; edit it if DHCP assigned a different address. Use the API Cloudflare hostname rather than the SSH hostname. Application credentials are entered at login and are held in memory only.

If direct LAN access already works, no listener changes are needed. If the gateway API still binds only to 127.0.0.1:8000, the optional gateway/enable-direct-api.sh helper changes the backend Uvicorn listener to 0.0.0.0:8000 and restarts the application service once. That listener accepts IPv4 connections on all gateway interfaces. Authentication and role checks still apply. The existing Cloudflare origin at 127.0.0.1:8000 continues to work. The helper does not modify WiFi, Ethernet, firewall, Cloudflare or hardware write settings.

Cloudflare's connector runs as a gateway service. This app does not implement interactive Cloudflare Access browser login or embed service secrets; the API hostname's Access policy must permit the intended client. A Cloudflare 530/handshake failure needs network/tunnel diagnosis.

## Windows development and release

Use Flutter stable and the Windows Visual Studio Desktop development with C++ toolchain. The full validation/build scripts stop on native command failures:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_windows.ps1
powershell -ExecutionPolicy Bypass -File .\build_windows_release.ps1
```

The release script packages the entire build/windows/x64/runner/Release folder into dist. Distribute that bundle, including DLLs and data, rather than the EXE alone. Existing EXEs must be rebuilt to include source updates. A fresh pubspec.lock is resolved on your machine; stale Windows caches/build outputs are excluded.

Official Windows setup: https://docs.flutter.dev/platform-integration/windows/setup

## Other functionality retained

The app retains customer/internal login, normalized four-pair monitoring, alarms/history, historian, diagnostics, internal-role control gates and the ACREL APM520 meter section with 34 measurements/energy counters and recent history. Telemetry uses WebSocket updates and periodic cached REST refresh; meter history refreshes while its screen is selected.

The backend remains responsible for Modbus polling, data quality, storage, authorization, control sequencing and cloud pushes. Viewing this app does not enable central-sync uploads, configure WiFi or alter field control gates. The separate WiFi configuration desktop app is not merged into this dashboard.

The meter section requires the installed kalpa-acrel-meter-v0.1 backend integration. Hardware scaling/direction still needs physical commissioning. The bundled BESS fixtures are simulated. This UI update does not establish that field pairs are commissioned or resolve the pending BMS startup/vendor questions.

Windows is the primary target. Android runner source is retained but packaging/signing/device behavior is unverified and its Gradle wrapper may require regeneration. Web is unsupported by the dart:io transport. Legacy Kinetics screen files are retained for reference; active asset navigation now opens the categorized Kalpa screen.

## Display catalog maintenance

To regenerate display metadata after updating the protocol catalogs in an isolated backend checkout:

```powershell
python tool/generate_kalpa_display_catalog.py C:\path\to\kalpa-backend
```

The generator reads generated_protocols/lineage_bms_catalog.json and elecod_pcs_catalog.json. It copies descriptions, units, addresses, enum/bit meanings and category metadata; it does not copy runtime values or scale factors. Review catalog changes and rerun the category contract check after regeneration.

See VALIDATION.md for the checks completed here and remaining Windows verification.
