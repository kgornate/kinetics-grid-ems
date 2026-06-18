# Flutter Upgrade Step 6 - Logs UI Cleanup

## Goal

Make the logs screen align with the backend's stable log query/filter abstraction while preserving the existing logs UI behavior.

## What changed

Added a small logs feature layer:

```text
lib/features/logs/log_field_catalog.dart
lib/features/logs/controllers/log_filter_builder.dart
lib/features/logs/widgets/log_storage_cards.dart
```

Updated:

```text
lib/screens/logs_screen.dart
lib/repositories/log_repository.dart
lib/features/logs/widgets/widgets.dart
```

Added test:

```text
test/log_filter_builder_test.dart
```

## Why this helps

Previously, `logs_screen.dart` contained field catalogs, filter mapping logic, storage widgets, and API query construction together.

Now these responsibilities are separated:

```text
LogsScreen
  -> UI state and screen layout

LogFieldCatalog
  -> telemetry/event/error column lists and default field selections

LogFilterBuilder
  -> converts UI filter selections into backend-aligned LogFilterModel

LogRepository
  -> calls log APIs using typed filters

Log storage widgets
  -> reusable storage status, log files, and metadata cards
```

## Backend alignment

The Flutter logs flow now maps cleanly to the backend log filter abstraction:

```text
Flutter UI filter controls
        |
        v
LogFilterBuilder
        |
        v
LogFilterModel
        |
        v
LogRepository
        |
        v
Backend /api/logs/telemetry, /api/logs/events, /api/logs/errors
```

## Existing behavior preserved

The following existing logs features remain supported:

```text
asset selection
log date selection
row limit selection
telemetry field selection
date filter
time range filter
search filter
status filters
PCS vendor/command filters
event filters
error filters
CSV download URL
storage status tab
log files tab
metadata card
```

## What this prepares for

This step prepares the logs screen for a future full UI split where `logs_screen.dart` can be reduced further into controller/view sections, but without forcing a risky visual change now.
