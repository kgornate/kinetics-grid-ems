# Flutter Upgrade Step 5: Dynamic Asset Dashboard Layer

## Goal

Add a backend-aligned dynamic asset catalog panel to the dashboard while preserving the existing fixed PCS/BMS/chiller dashboard sections.

This lets the Flutter app begin consuming the latest EMS gateway backend APIs:

```text
GET /api/assets
GET /api/health/assets
```

without removing the current UDP-based dashboard flow.

## What was added

New widgets:

```text
lib/features/assets/widgets/
  asset_status_helpers.dart
  asset_health_chip.dart
  dynamic_asset_card.dart
  dynamic_asset_summary_panel.dart
  widgets.dart
```

Updated:

```text
lib/screens/dashboard_screen.dart
```

Added test:

```text
test/dynamic_asset_widget_test.dart
```

## What the dashboard now does

The main dashboard now shows a new section near the top:

```text
Dynamic Asset Runtime
```

This section fetches:

```text
/api/assets
/api/health/assets
```

and displays dynamic asset cards with:

```text
asset_id
asset_type
vendor
protocol
runtime_mode
enabled/running/online flags
health status
recommended action
```

## Existing behavior preserved

The existing dashboard sections remain unchanged:

```text
BMS / Battery Telemetry
PCS / Inverter Telemetry
Chiller Telemetry
Command Panel
Raw Packet Card
Logs screen
PCS screen
BMS screen
```

UDP telemetry continues to drive the existing fixed cards.

## Why this matters

Backend is now asset-list aware. Flutter can now start moving away from hardcoded PCS/BMS/chiller assumptions.

Current behavior:

```text
Fixed cards still work.
Dynamic asset panel is added above them.
```

Future behavior:

```text
Dashboard can render assets dynamically from /api/assets.
New assets such as pcs_2, bms_2, meter_1, relay_1, inverter_1 can appear without large UI rewrites.
```

## Current limitation

This step does not remove the old fixed dashboard UI. That is intentional.

This step adds the dynamic catalog layer first, so we can verify backend compatibility before migrating the entire UI to fully dynamic asset cards.
