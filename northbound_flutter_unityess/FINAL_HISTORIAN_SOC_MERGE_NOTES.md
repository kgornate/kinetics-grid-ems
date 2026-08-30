# Final cumulative Flutter merge - Historian + SOC/Solis Control

This source tree preserves both feature lines in one build.

## Historian restored

- Top navigation includes `Historian`.
- `FastBessHistorianScreen` is connected through `DashboardShellScreen`.
- Fast BESS API client methods are restored:
  - `GET /api/fast-bess/status`
  - `GET /api/fast-bess/profile`
  - `GET /api/fast-bess/latest`
  - `GET /api/fast-bess/history`
- Existing BESS/source, PCS/BMS signal and date/time filters are preserved.
- Table-only and paginated full-range loading are preserved.
- CSV and XLSX downloads are preserved.
- `archive` dependency is restored for XLSX generation.

## SOC / Solis control preserved

- Live BESS X/Y SOC and target state.
- Solis target/state/power/communication status.
- Controller state, decision and warnings.
- Controller/Solis history.
- Runtime threshold display.
- Internal-admin-only threshold editing.
- Customer read-only threshold/status access.

## Build

From the project root on Windows:

```powershell
flutter clean
flutter pub get
flutter run -d windows
```

Expected top navigation includes both `Historian` and `SOC Control`.
