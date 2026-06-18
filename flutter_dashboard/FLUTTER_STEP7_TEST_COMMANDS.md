# Flutter Step 7 Test Commands

Run from the Flutter dashboard folder on Windows:

```powershell
cd C:\Users\KunalGupta\EMS_Ornte_Code_base\kinetics-grid-ems\flutter_dashboard

flutter clean
flutter pub get
flutter analyze
flutter test test\repository_construction_test.dart
flutter test test\dynamic_asset_widget_test.dart
flutter test test\log_filter_builder_test.dart
flutter test test\command_catalog_test.dart
flutter run -d windows
```

Manual checks:

```text
Dashboard opens successfully.
Existing command panel buttons are visible.
Read Chiller, Read PCS, Read BMS still work.
PCS set active power command still works.
BMS fan/read controls still work.
PCS screen command panel still works.
Logs screen filters still work.
Dynamic Asset Runtime panel still works.
```
