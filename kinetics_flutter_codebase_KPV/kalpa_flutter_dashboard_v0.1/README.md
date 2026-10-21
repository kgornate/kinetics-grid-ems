# Kalpa Gateway Flutter Dashboard v0.1

Windows desktop source release adapted from the supplied Kinetics Flutter dashboard for the current Kalpa DEBIX backend. No gateway configuration files or credentials are included. This is a source package, not a compiled installer.

## What is included

- Authenticated login with gateway username/password and configurable API URL; credentials are held in memory only.
- Kalpa normalized overview, Lineage system BMS and four racks, four Elecod PCS, four pair summaries, and auxiliary assets.
- Searchable, paginated raw signal tables, including cell signals and decoding metadata. Normalized engineering values are used for headline readings; Kinetics scaling is not applied to Kalpa values.
- ACREL APM520 section: all 34 measurements/energy counters, communication errors, hardware/mock source, commissioning notice, and recent stored history.
- Alarms/history, historian, polling/storage/data-rate diagnostics, and the existing internal-role control workflow adapted to Kalpa capability and status shapes.
- Live WebSocket telemetry plus periodic REST refresh and REST fallback. Normalized/meter REST refresh is every 5 seconds; meter history every 15 seconds while its tab is selected. These read cached backend data rather than directly polling Modbus devices.
- Unavailable/stale normalized and meter readings are masked. Compact control records without write gates never authorize control. The gateway remains the authority for role, write and commissioning gates.

## 1. Windows prerequisites

Install Flutter stable on Windows and Visual Studio with the **Desktop development with C++** workload. Put Flutter on PATH. Run `flutter doctor -v` and resolve Windows toolchain issues. Native Windows builds must be performed on Windows.

Official setup: https://docs.flutter.dev/platform-integration/windows/setup

## 2. Direct connection — no SSH tunnel required

The app communicates directly with the Kalpa HTTP API and WebSocket telemetry using the entered gateway URL and customer/internal application credentials. SSH is only an optional administration tool; no terminal needs to remain open during normal app use.

| Connection | App API URL | Requirement |
| --- | --- | --- |
| PC Ethernet to eth0 | http://192.168.10.2:8000 | PC 192.168.10.1/24, gateway eth0 192.168.10.2/24 |
| Same WiFi/LAN | http://GATEWAY_WIFI_IP:8000 | Use the gateway's current WiFi IPv4 address |
| Remote Cloudflare | https://gw3-api.unityess.cloud | Gateway WiFi/internet and cloudflared service online |

The WiFi preset uses the last known example address 192.168.0.122; edit it if the gateway received another DHCP address. The Cloudflare hostname is the API hostname, not the SSH hostname.

### One-time gateway listener setting

The archived gateway service binds port 8000 to 127.0.0.1. This prevents direct Ethernet/WiFi requests, regardless of the app. If the running service still uses that setting, run the included `gateway/enable-direct-api.sh` **on the gateway** as root. It installs a dedicated systemd drop-in that changes the existing Uvicorn listener to 0.0.0.0:8000 and restarts only the application backend. This listens on all gateway IPv4 interfaces, including field Ethernet; existing application authentication and role checks remain required. No firewall, WiFi, Ethernet, Cloudflare or hardware write-gate settings are changed. The current Cloudflare origin at 127.0.0.1:8000 continues to work with this listener.

Example transfer from Windows, followed by a one-time SSH command:

```powershell
scp -O .\gateway\enable-direct-api.sh root@192.168.10.2:/root/
ssh root@192.168.10.2 "bash /root/enable-direct-api.sh"
```

After that command returns, close PowerShell if desired. The drop-in persists after reboot. The helper checks that the expected backend executable exists and verifies a TCP connection through eth0 after restarting. If it fails, inspect service logs; rollback is printed by the helper. If the backend already listens on a reachable address, this step is unnecessary.

Cloudflare's connector runs as a **gateway service**, not a laptop SSH tunnel. A separate Cloudflare Access policy can still intercept API requests: this app does not implement interactive browser Access login or embed service secrets. The hostname must allow the intended authenticated API/WebSocket client. A Cloudflare 530/handshake error needs tunnel/network diagnosis; application credentials cannot fix it.

## 3. Run the app

Extract the ZIP and open PowerShell in the folder containing pubspec.yaml:

```powershell
flutter pub get
flutter analyze --no-fatal-infos
flutter test
dart run tool/offline_contract_check.dart
flutter run -d windows
```

The login defaults to username `customer`; enter the configured application password. For the internal control view, use the configured internal account. SSH authentication and application authentication are separate. No application password is bundled.

If PowerShell native commands fail, stop and resolve the first error. The supplied scripts check exit codes and stop automatically:

```powershell
powershell -ExecutionPolicy Bypass -File .
un_windows.ps1
```

## 4. Make a Windows release

```powershell
powershell -ExecutionPolicy Bypass -File .uild_windows_release.ps1
```

The script resolves dependencies, analyzes, tests, runs contract checks, builds Windows release, and ZIPs the **entire** runner Release folder into dist. Distribute that ZIP, not the EXE alone: Flutter DLLs and data are required. A resolved pubspec.lock will be generated by Flutter on your machine; the uploaded project's stale SDK lock/cache is intentionally excluded.

## Backend prerequisites and scope

The Kalpa backend must be running and expose /api/auth/login, /api/telemetry/compact, /api/normalized/snapshot, /ws/telemetry and the existing alarm/historian/diagnostic endpoints. The meter section requires the installed kalpa-acrel-meter-v0.1 integration exposing /api/meters. A missing meter route is shown as unavailable without hiding battery/PCS data. History requires stored samples.

This app runs on the laptop. It does not install Flutter on DEBIX or replace the gateway web HMI. The desktop app does not change backend services, cloud upload configuration, WiFi/SSH setup or hardware write gates. The optional one-time gateway listener helper only changes API binding. WiFi configuration GUI from the separate connectivity application is not merged into this dashboard release. Cloud push stays in the gateway central-sync service; viewing this app does not enable uploads.

Hardware commissioning is separate: BESS fixtures are simulated, and the ACREL live voltage/current scaling still needs comparison with the physical meter. This package does not establish that all four field pairs are commissioned or safe to control.

Windows is the primary target. The supplied Android runner source is retained for future work; Android packaging, signing and device testing are unverified, and its missing Gradle wrapper may need regeneration with Flutter. Web is not supported by the current dart:io client. Legacy Kinetics detail-screen source remains for reference but the Kalpa home navigation uses the new normalized screens and generic raw-signal view.

See VALIDATION.md for exact checks and limitations.
