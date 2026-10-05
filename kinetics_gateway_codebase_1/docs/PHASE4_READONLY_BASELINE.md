# Phase 4 - Elecod + Lineage Live Read-Only Gateway Baseline

## Status

Phase 4 is the first build intended to be placed on the real gateway and connected to the Elecod PCS + Lineage BMS network for **read-only commissioning**.

It is a **complete gateway codebase**, copied forward from the field-validated Kinetics baseline and Phase-3 migration tree. It is not a loose patch set and does not require manual copy/paste of individual Python files.

## What is integrated end-to-end

- Lineage system/BAMS polling through the existing `GatewayService`.
- Lineage Rack 1..4 polling through the existing fast/normal/slow/bulk scheduler.
- Lineage FC02 alarm/discrete-input processing in the existing alarm lifecycle/historian.
- Elecod PCS 1..4 polling through the existing multi-PCS runtime cache.
- Existing REST APIs, WebSocket telemetry, SQLite historian, alarm history, asset APIs and diagnostics remain in place.
- New vendor-neutral cached view at `/api/normalized/snapshot`.
- New normalized pair view at `/api/normalized/pairs`.
- Internal read-only commissioning status at `/api/commissioning/read-only`.
- Phase-4 direct fieldbus commissioning probe at `tools/phase4_readonly_commission.py`.
- Complete writes/control remain disabled in the Phase-4 config.

## Lineage topology correction

For `architecture=system_rack`, the gateway now polls:

```text
Lineage System/BAMS   -> one endpoint / Unit ID 1
Lineage Rack 1        -> configured Rack 1 Unit ID
Lineage Rack 2        -> configured Rack 2 Unit ID
Lineage Rack 3        -> configured Rack 3 Unit ID
Lineage Rack 4        -> configured Rack 4 Unit ID
```

The Kinetics three-level behavior with one pair-specific BAU per TCP endpoint remains backward compatible and is used only when `architecture=three_level`.

## Auxiliary devices

The V05 workbook contains Temp/Humidity, water sensor, chiller and dehumidifier register groups, but it does not unambiguously define the final per-device Unit-ID allocation.

Phase 4 therefore supports configurable auxiliary endpoints:

```json
{
  "asset_id": "chiller_1",
  "category": "chiller",
  "port": 502,
  "unit_id": 101,
  "enabled": true
}
```

No Unit-ID allocation is invented in the default Phase-4 template. `poll_environment_enabled` is false until commissioning/vendor information supplies the final routing.

## Commissioning gates that are intentionally NOT guessed

1. Lineage FLOAT32 word order.
2. Lineage current positive/negative direction.
3. Modbus address-offset convention on installed firmware.
4. Final Lineage auxiliary Unit-ID allocation.
5. Elecod positive/negative active-power direction.
6. Elecod write-function behavior on installed firmware.
7. Lineage approved startup/precharge sequence.
8. Lineage normal-operation contactor command semantics.

Items 5-8 belong to Phase 5 because Phase 4 never performs production writes.

## Validation

Automated regression result for this package:

`69 passed, 0 failed`

This includes all original Kinetics regression tests plus Phase-3 and Phase-4 Elecod/Lineage migration tests.
