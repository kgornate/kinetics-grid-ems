# Phase F2 - Fast BESS Historian UI

This patch adds a read-only Fast BESS Historian screen to the Northbound Flutter dashboard.

## Purpose

Phase F2 integrates the backend compact logger APIs into Flutter so the operator/team can view 1-second PCS/BMS compact logger data without loading the full 90-day database into the UI.

## Added UI

New dashboard navigation item:

- Historian

New screen:

- `lib/features/dashboard/screens/fast_bess_historian_screen.dart`

The screen shows:

- Fast logger runtime status
- Latest BESS 1 and BESS 2 compact samples
- Filter panel
- Parameter selector for PCS/BMS signals
- History table with selected time range, source, asset type, row limit, and order

## Backend APIs used

- `GET /api/fast-bess/status`
- `GET /api/fast-bess/profile`
- `GET /api/fast-bess/latest?format=compact`
- `GET /api/fast-bess/history?format=compact&limit=...&source_id=...&from_epoch_ms=...&to_epoch_ms=...&order=...`

## Important behavior

The screen does not automatically pull huge history. It loads status/latest first, then the user must click `Load history`. This prevents Flutter from trying to render 90 days of 1-second data.

## What is not included in F2

- Excel/CSV download is intentionally left for Phase F3.
- Charts/trends are intentionally left for later.
- Custom date-time picker is not included yet; F2 uses safe preset ranges: 5 min, 15 min, 1 hour, 6 hours, 24 hours.

## Expected validation

Run:

```powershell
flutter analyze
flutter run -d chrome
flutter run -d windows
```

Then verify:

1. Login works.
2. Existing Home/PCS/BMS pages still work.
3. New `Historian` navigation button appears.
4. Historian page opens.
5. Logger status shows `running=true`, `execution_mode=threaded`, `write_mode=value_only`.
6. Latest samples show BESS 1 and BESS 2.
7. Select filters and click `Load history`.
8. Table shows timestamp, BESS, quality, age, and selected PCS/BMS parameters.
