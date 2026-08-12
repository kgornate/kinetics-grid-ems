# Phase F3 Export Safe Patch

This patch is meant to be applied over the working Phase F2 Historian + Persistent Navigation app.

It adds CSV/XLSX export for the currently loaded historian table and fixes the red runtime widget error seen in the historian filter section:

`type 'double' is not a subtype of type 'bool' in type cast`

The fix replaces the inline FilterChip/ExpansionTile parameter selector with a safer dialog-based parameter selector. The user can still select PCS/BMS parameters, default critical parameters, all shown parameters, or clear selection.

The patch also keeps the persistent navigation behavior so already-opened pages remain alive when switching menus.

## Files included

- lib/core/api/northbound_api_client.dart
- lib/core/download/*
- lib/core/export/fast_bess_history_exporter.dart
- lib/features/dashboard/screens/dashboard_shell_screen.dart
- lib/features/dashboard/screens/fast_bess_historian_screen.dart
- lib/features/dashboard/widgets/dashboard_nav_actions.dart
- pubspec.yaml

## Test flow

1. flutter clean
2. flutter pub get
3. flutter analyze
4. flutter run -d chrome
5. Open Historian
6. Load history
7. Choose parameters
8. Download CSV
9. Download Excel
