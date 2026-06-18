# Flutter Upgrade Step 7: Command Layer Cleanup

## Goal

Centralize gateway command strings, command metadata, UI helper logic, and command response classification so future command panels can be generated or validated from one shared catalog.

## Added files

```text
lib/features/commands/
  command_catalog.dart
  command_definition.dart
  command_result_mapper.dart
  command_ui_helpers.dart
  gateway_command_names.dart
  commands.dart
```

## Updated areas

```text
lib/widgets/command_panel.dart
lib/widgets/pcs_command_panel.dart
lib/services/bms_service.dart
lib/repositories/command_repository.dart
lib/screens/dashboard_screen.dart
lib/screens/pcs_screen.dart
```

Existing UI behavior is preserved. The current command panels still render the same controls, but raw command strings are now centralized through `GatewayCommandNames` and metadata lives in `CommandCatalog`.

## Benefits

```text
Command strings are centralized.
PCS/BMS/chiller command metadata is reusable.
Future asset command panels can be catalog-driven.
Command value validation has a shared helper layer.
Command result routing can use command families instead of scattered string checks.
```

## Test

```powershell
flutter clean
flutter pub get
flutter analyze
flutter test test\repository_construction_test.dart
flutter test test\dynamic_asset_widget_test.dart
flutter test test\log_filter_builder_test.dart
flutter test test\command_catalog_test.dart
flutter run -d windows
```
