# Flutter Upgrade Step 4 - Screen Decomposition

## Goal

This step starts breaking large UI files into smaller reusable feature widgets while preserving the existing dashboard behavior.

The current UI still works with the existing UDP/TCP/log services, but the most repeated layout pieces are now moved into feature-level widget folders.

## Added folders

```text
lib/features/dashboard/widgets/
lib/features/logs/widgets/
```

## Dashboard widgets added

```text
lib/features/dashboard/widgets/dashboard_section_header.dart
lib/features/dashboard/widgets/gateway_config_card.dart
lib/features/dashboard/widgets/dashboard_status_row.dart
lib/features/dashboard/widgets/bms_telemetry_grid.dart
lib/features/dashboard/widgets/pcs_telemetry_grid.dart
lib/features/dashboard/widgets/chiller_telemetry_grid.dart
lib/features/dashboard/widgets/raw_packet_card.dart
lib/features/dashboard/widgets/dashboard_formatters.dart
lib/features/dashboard/widgets/widgets.dart
```

## Logs widgets added

```text
lib/features/logs/widgets/log_data_table.dart
lib/features/logs/widgets/log_empty_state.dart
lib/features/logs/widgets/log_info_row.dart
lib/features/logs/widgets/widgets.dart
```

## Updated files

```text
lib/screens/dashboard_screen.dart
lib/screens/logs_screen.dart
```

## What changed

`dashboard_screen.dart` now delegates these UI sections to feature widgets:

```text
Gateway config card
Status indicator row
BMS telemetry grid
PCS telemetry grid
Chiller telemetry grid
Raw UDP packet card
Section headers
```

`logs_screen.dart` now delegates these UI pieces:

```text
Log data table
Empty state card
Info row
```

## Why this helps

Before this step, screens contained too much UI construction directly inside one large file. After this step, the app has a better feature-oriented structure:

```text
screens/ -> page state and flow
features/.../widgets/ -> reusable UI sections
models/ -> typed backend models
repositories/ -> backend access layer
core/ -> API/config/network utilities
```

This makes future frontend work easier:

```text
Dynamic asset cards
Health cards
Operator telemetry screens
Reusable log tables
Cleaner UI testing
Smaller screen files
```

## Compatibility

No intentional behavior changes were made.

Existing flows should still work:

```text
UDP telemetry dashboard
TCP command panel
PCS detail screen
BMS detail screen
Logs screen and filters
Raw packet display
Last command result display
```
