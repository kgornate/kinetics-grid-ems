# Phase F1 - Flutter performance stabilization patch

This patch is intentionally limited to dashboard performance stabilization before adding the Fast BESS Historian screen.

## What changed

1. `dashboard_shell_screen.dart`
   - Removed the eager `IndexedStack` page creation.
   - The shell now builds only the currently selected page.
   - Hidden dashboard pages are disposed when user navigates away, so their polling timers stop immediately.
   - This avoids the previous behavior where Home, PCS, BMS, Chiller, Dehumidifier, Fire, Meter, EMS, and Strategy pages could all run API polling in the background.

2. `northbound_api_client.dart`
   - Added a 60-second in-memory cache for `/api/sources/summary`.
   - Added a 60-second in-memory cache for `/api/assets?source_id=...`.
   - Repeated PCS/BMS page loads no longer refetch mostly static source/asset mapping on every refresh cycle.
   - Added `NorthboundApiClient.clearCaches()` for future logout/session reset usage.

## Why this is Phase F1

The historian screen will query 1-second logging data. Before adding that, the existing dashboard must stop doing unnecessary background API polling. This patch reduces first-load and page-switching pressure without changing existing PCS/BMS display logic.

## What is not changed yet

- No Fast BESS Historian screen yet.
- No Excel/CSV download yet.
- No charting yet.
- No backend historian API changes.
- PCS/BMS telemetry parsing logic is kept as-is.

## Recommended validation

Run:

```bash
flutter clean
flutter pub get
flutter analyze
flutter run -d chrome
```

Manual validation:

1. Login.
2. Check Home page loads.
3. Navigate to PCS and BMS.
4. Confirm inactive pages stop polling by watching backend API logs.
5. Confirm source/asset list calls reduce after first minute due cache.
6. Confirm control/strategy page still opens.

## Rollback

Restore these files from backup:

- `lib/features/dashboard/screens/dashboard_shell_screen.dart`
- `lib/core/api/northbound_api_client.dart`
