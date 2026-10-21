# Validation — Kalpa Flutter dashboard v0.1

## Completed in this environment

- Dart format parsed all 27 Dart source/test/tool files.
- Offline Dart static analysis of lib/ against actual Flutter framework and engine UI sources: zero errors, zero warnings; informational lints/deprecations remain in inherited/new code. This is not a Flutter build.
- 27 executable pure-Dart contract checks passed using fixtures generated from an isolated current Kalpa backend with all hardware writes disabled.
- Checks cover four racks/four PCS, normalized four-pair values, canonical Lineage signals, meter snapshot/delta/removal, auxiliary exclusion, Kalpa commissioning gates, compact-control fail-closed behavior, invalid base URLs, authenticated REST and WebSocket loopback transport, URL path prefixes, HTTP 530 reporting and absence of field-control writes, and the direct Ethernet URL default.
- Fixtures were produced by the backend service functions, not captured from operating field hardware. The HTTP transport portion uses a local loopback server; it does not demonstrate live Cloudflare/gateway connectivity.

## Not completed here

The Flutter tool attempted to probe the cloud metadata address 169.254.169.254; automatic approval review blocked that action. It was not retried. Flutter widget/model test execution, graphical rendering and native builds therefore remain unverified. Direct Dart checks and offline analysis were used separately. No Windows EXE or Android APK is included.

Run the included Windows script to perform flutter analyze, flutter test, contract checks and the native release build. The three new widget/formatter tests are included but have not been executed here. Existing model/presentation Flutter tests are retained; their execution also awaits that Windows run.

## Site acceptance after building

1. Enable the direct listener if needed, close all SSH sessions, log in at http://192.168.10.2:8000 and confirm four rack/PCS pairs and raw signals.
2. Confirm the customer account has no control tab. Confirm disabled backend gates cannot enable commands for the internal account. Do not enable hardware writes solely to test UI.
3. Connect the ACREL meter and confirm online status, all relevant measurements and subsequent history samples. Compare energized measurements and direction against the physical display before accepting scaling.
4. Disconnect the meter and confirm unavailable values are masked while BESS screens remain available.
5. Unplug/reconnect Ethernet and confirm disconnection and recovery without fabricated zero readings. Repeat over WiFi IP and the Cloudflare API hostname without a laptop SSH tunnel.
6. Close/reopen the desktop app: password should be requested again. Production upload and network settings should be unchanged; the optional API listener drop-in should persist after reboot.
