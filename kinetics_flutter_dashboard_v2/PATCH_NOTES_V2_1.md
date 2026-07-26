# Kinetics Flutter Dashboard V2.1 patch notes

## Engineering mapping fixes

- Rack `soc`, `soh`, and `rack_inner_soc` are converted from per-mille to percent.
- Rack cards now use the correct `vrack` and `irack` points.
- Broken units from the source payload are normalized (`°C`, `‰`, `kΩ`, `mΩ`, `Ω/V`, `kvar`, `kVA`).
- Energy-meter U32 payloads are temporarily decoded as IEEE-754 float32 in Flutter, so the current backend can be tested without first deploying the backend patch.
- BAU bank voltage/current cards transparently fall back to rack-derived values when the BAU registers report zero. The UI labels these values as derived rather than pretending the BAU supplied them.

## Visual redesign

- Expanded overview with bank limits, online state, alarms, and richer rack/environment cards.
- Dedicated BAU dashboard with summary cards and categorized sections.
- Rack detail tabs for overview, electrical, thermal, cells, sensors, alarms/faults, and all signals.
- Full cell-channel table with voltage, temperature channel, deviation, paging, and basic outlier highlighting.
- Separate terminal, busbar, and coolant sensor sections.
- Categorized HVAC, liquid-cooling, energy-meter, dehumidifier, and safety-I/O detail views.
- Friendly engineering names and register metadata in searchable tables.

## Important interpretation note

The live payload contains 416 populated cell-voltage channels and 240 populated temperature channels per rack. It does not include a complete one-to-one mapping between every cell and every temperature sensor. The cell table therefore shows temperature by matching channel index when present and `--` otherwise. Dedicated sensor sections preserve the complete arrays without inventing a mapping.
