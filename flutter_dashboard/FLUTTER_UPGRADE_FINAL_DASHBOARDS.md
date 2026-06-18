# Flutter Upgrade: Health, Storage, Operator, and Dynamic Asset Pages

## Goal

This update turns the backend support already added in the EMS gateway into visible Flutter dashboard pages.

The app now exposes product-level screens for:

```text
Health Dashboard
Storage Health Page
Operator Mode Dashboard
Dynamic Asset Navigation
Asset Detail Page
```

Existing fixed dashboard behavior is preserved:

```text
UDP telemetry
TCP commands
PCS screen
BMS screen
Logs screen
Existing telemetry cards
Existing command panels
```

## New screens

```text
lib/screens/health_dashboard_screen.dart
lib/screens/storage_health_screen.dart
lib/screens/operator_dashboard_screen.dart
lib/screens/asset_navigation_screen.dart
lib/screens/asset_detail_screen.dart
```

## New reusable monitoring widgets

```text
lib/features/monitoring/widgets/
  key_value_table.dart
  json_preview_card.dart
  status_summary_card.dart
  monitoring_widgets.dart
```

## Dashboard navigation updates

`lib/screens/dashboard_screen.dart` now has AppBar shortcuts for:

```text
Operator
Assets
Health
Storage
Logs
```

The existing dynamic asset panel now opens the generic `AssetDetailScreen` instead of only routing PCS/BMS assets to fixed screens. Fixed PCS and BMS detail screens still remain available from their existing buttons.

## Backend APIs used

```text
GET /api/assets
GET /api/assets/{asset_id}
GET /api/telemetry/operator
GET /api/assets/{asset_id}/telemetry/operator
GET /api/health
GET /api/health/assets
GET /api/health/assets/{asset_id}
GET /api/diagnostics
GET /api/diagnostics/assets/{asset_id}
GET /api/storage/health?asset_id={asset_id}
```

## What each page does

### Health Dashboard

Shows:

```text
gateway health
asset health
recommended actions
diagnostics summary
raw expandable health JSON
```

### Storage Health Page

Shows per-asset storage information from the Log HTTP API:

```text
storage status
base path
telemetry files count
latest telemetry file
disk usage
log sizes
```

### Operator Mode Dashboard

Uses the backend operator telemetry API so noisy fields such as raw registers and storage logger internals stay hidden.

Shows:

```text
operator telemetry summary
asset-wise operator telemetry cards
asset health chips
recommended actions
operator JSON preview
```

### Dynamic Asset Navigation

Uses `/api/assets` and `/api/health/assets` to render the asset list dynamically.

### Asset Detail Page

For any asset from the backend catalog, shows:

```text
asset profile/runtime details
operator telemetry
health
diagnostics
storage health
expandable JSON blocks
```

## Compatibility

No backend API changes are required. This update consumes APIs already provided by the stable EMS gateway backend.

No existing fixed UI flow is removed.
