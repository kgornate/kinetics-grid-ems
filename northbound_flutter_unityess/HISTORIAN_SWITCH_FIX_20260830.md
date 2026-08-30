# Historian navigation switch fix - 2026-08-30

Flutter compile error fixed:

`DashboardPage` gained the `historian` enum value, but seven legacy fallback navigation
switches were not updated. Dart requires enum switches to be exhaustive.

Added `DashboardPage.historian` -> `FastBessHistorianScreen` in:

- dehumidifier_screen.dart
- fire_screen.dart
- liquid_cooling_screen.dart
- pcs_screen.dart
- utility_meter_screen.dart
- ems_system_screen.dart
- strategy_command_screen.dart

Also added the historian screen import to those seven files.

The persistent DashboardShell historian page, Historian top-nav button, Fast BESS API
client methods, CSV/XLSX exporter and archive dependency remain present.
