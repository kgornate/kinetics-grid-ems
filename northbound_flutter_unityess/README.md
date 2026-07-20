Phase 4.5 BMS direct-summary mapping fix

Changes:
- BMS page now requests full asset telemetry with compact=false for the BMS detail page.
- Max/min cell voltage now prefer direct summary fields like max_voltage_value_at_shutdown and min_voltage_value_at_shutdown, with cell_voltage_* derivation only as fallback.
- Max/min temperature now prefer direct summary fields like max_cell_temperature_at_shutdown and min_cell_temperature_at_shutdown, with measured temperature channels as fallback.
- Direct summary IDs at shutdown are preferred for max/min voltage and temperature IDs.
- Cluster resistance no longer hides a valid 0.0 value if that is what telemetry reports.
