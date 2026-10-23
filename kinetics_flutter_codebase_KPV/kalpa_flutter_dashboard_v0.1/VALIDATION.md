# Validation — categorized Kalpa asset dashboards, 23 October 2026

## Completed for this update

- 135 executable standalone Dart category/formatting checks passed. These cover all 3,892 generated protocol metadata definitions, every published fixture point, reachable category tabs, all four racks and PCS devices, all environment assets, numeric channel ordering, enum labels, restored units/addresses, separate settings and alarm classification, missing/bad/offline masking and preservation of signed/zero engineering values.
- The rack fixture retains all 2,272 points: 416 cell voltages, 416 cell temperatures, 416 cell SOC points and 832 charge/discharge balancing points, plus rack/sensor/alarm signals. Channel counts describe this simulated fixture, not a physical rack guarantee.
- All 27 existing standalone model/API contract checks passed again, including loopback authenticated REST and WebSocket transport, direct Ethernet defaults, HTTP errors, meter ingestion and fail-closed control gates.
- Offline Dart static analysis against the actual Flutter framework/engine UI sources found zero errors and zero warnings in lib/ and test/. Informational inherited/new lints remain. This is source analysis, not a Flutter build.
- Dart format parsed the updated source/test/tool files. ZIP integrity and exact source inclusion were checked.

Fixtures were generated from isolated backend service functions with hardware writes disabled. Loopback transport checks do not demonstrate live gateway/Cloudflare connectivity.

## Still to verify on Windows

Twelve widget regressions are included: four rack routes at desktop/narrow widths, Cells/Sensors tabs, live cell updates/search, missing assets, PCS tab separation and environment measurement/settings separation. These tests have not been executed here. Graphical rendering and native Windows/Android builds remain unverified.

An earlier Flutter-tool invocation was blocked by automatic approval review when it attempted a cloud metadata probe. It was not retried. Current checks used the standalone Dart SDK and Flutter source files without invoking the Flutter tool.

Run:

```powershell
flutter pub get
flutter analyze --no-fatal-infos
flutter test
dart run tool/offline_contract_check.dart
dart run tool/kalpa_category_contract_check.dart
flutter run -d windows
```

Inspect all four rack detail dashboards, each PCS, System BMS and every environment asset. Confirm category tables, tab switching, scrolling, search, pagination, decoded flag labels and back navigation. Disconnect a physical meter to verify its independent offline behavior. Source/backend metadata determines units; energized measurements still need comparison with actual hardware.

No gateway configuration, physical control interlock, field topology, cloud upload settings or WiFi settings were changed by this UI update.
