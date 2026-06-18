# Flutter Step 6 Test Commands

Run from the Flutter dashboard folder on Windows:

```powershell
cd C:\Users\KunalGupta\EMS_Ornte_Code_base\kinetics-grid-ems\flutter_dashboard
flutter clean
flutter pub get
flutter analyze
flutter test test\repository_construction_test.dart
flutter test test\dynamic_asset_widget_test.dart
flutter test test\log_filter_builder_test.dart
flutter run -d windows
```

## Manual checks

After the app starts:

```text
1. Dashboard opens normally.
2. Existing UDP telemetry still updates.
3. Dynamic Asset Runtime panel still appears.
4. Logs screen opens.
5. Asset dropdown works for chiller_1, pcs_1, bms_1.
6. Refresh Logs works.
7. Telemetry Only works.
8. Date filter works.
9. Start/end time filters work.
10. Field selection filter works.
11. Search filter works.
12. Event and error tabs still work.
13. Storage tab still shows storage status, files, and metadata.
14. CSV download URL still appears.
```

## Backend endpoints used

```text
/api/logs/assets
/api/storage/status
/api/logs/files
/api/logs/telemetry
/api/logs/events
/api/logs/errors
/api/logs/metadata
/api/logs/download/telemetry
```
