# NorthBound Flutter Dashboard v1.0 - Multi-source control update

This package updates the NorthBound Flutter dashboard for the two independent Unity261PV / Chinese EMS units controlled by the gateway.

## Backend expected

The dashboard expects the v1.2+ Northbound EMS Gateway backend with:

- `GET /api/sources`
- `GET /api/sources/summary`
- `GET /api/sources/{source_id}/assets`
- source-namespaced assets such as `external_ems_1_pcs` and `external_ems_2_bms`
- `GET /api/commands/ems/registers?source_id=...`
- `POST /api/commands/ems/write`
- `POST /api/control/sources/{source_id}/grid-mode`
- `POST /api/control/sources/{source_id}/charge`
- `POST /api/control/sources/{source_id}/discharge`
- `POST /api/control/sources/{source_id}/standby`
- `POST /api/control/site/grid-mode`
- `POST /api/control/site/power`
- `POST /api/control/site/standby`

## UI changes

- Dashboard now shows source cards for Chinese EMS 1 and Chinese EMS 2.
- Assets are grouped under their source instead of shown as one flat list.
- Internal users see a Control Panel button in the app bar.
- Internal users see an EMS Command Registers button for raw commissioning writes.
- Customer users keep read-only dashboard, alarms, logs, storage, and asset telemetry views.

## Control Panel behavior

Single EMS controls:

- Standby / zero power
- Switch grid-tied
- Switch off-grid
- Charge kW
- Discharge kW

Site controls:

- Both standby
- Both grid-tied
- Both off-grid sequentially using backend voltage-stability logic
- Both charge with equal allocation
- Both discharge with equal allocation

Grid/off-grid and power commands show a confirmation dialog before writing.

## Important source IDs

- `external_ems_1` = 192.168.100.151:502
- `external_ems_2` = 192.168.100.153:502

## Build/run

```bash
flutter pub get
flutter run -d windows
```

For release:

```bash
flutter build windows --release
```
