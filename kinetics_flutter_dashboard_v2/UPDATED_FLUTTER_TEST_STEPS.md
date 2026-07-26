# Kinetics Flutter Dashboard V2.1 – Test Steps

## Main improvements

- Correct rack SOC/SOH conversion from per-mille to percent.
- Correct rack voltage/current mapping (`vrack`, `irack`).
- Effective bank-voltage/current cards derived from rack values when BAU registers report zero.
- BAU summary cards and categorized engineering sections.
- Enhanced rack cards with voltage, current, SOC, SOH, cell limits, temperature and insulation.
- Rack detail tabs: Overview, Electrical, Thermal, Cells, Sensors, Alarms & faults, All signals.
- Full cell-voltage table with corresponding temperature-channel data when available.
- Environment asset cards and category-based detail pages.
- Temporary Flutter-side IEEE-754 decoding for energy-meter U32 payloads.
- Unit cleanup for °C, ‰, kΩ, mΩ, Ω/V, kvar and kVA.
- API timeout increased to 300 seconds.

## Run

```powershell
cd "C:\Users\KunalGupta\EMS_Ornte_Code_base\kinetics-grid-ems\kinetics_flutter_dashboard_v2_patched"
flutter clean
flutter pub get
flutter test
flutter run -d windows
```

## Login

- Base URL: `https://gw1-api.unityess.cloud`
- Username: `internal`
- Password: the password configured on the gateway

## First validation

1. Open **Overview** and verify rack SOC values appear near 92–93%, not 923–930%.
2. Verify rack voltage values appear near 1388–1390 V.
3. Open **BAU** and verify the effective bank voltage is derived from rack voltages when the BAU register remains 0 V.
4. Open each **Rack**, then select **Cells**. Use **Load complete rack data** if cell arrays are not yet populated.
5. Open **Environment → Energy meter** and verify values are realistic (roughly 235 V phase voltage, 408 V line voltage, 50 Hz in the captured dataset).
6. Open **Alarms & faults** inside each rack.

The Flutter-side meter correction is temporary. A backend patch is supplied separately so all consumers, including the IT/backend team, receive engineering values directly from the API.
