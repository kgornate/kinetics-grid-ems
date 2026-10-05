# Phase 3 - Elecod + Lineage Actual Codebase Baseline

## Status

Phase 3 is the first **actual source-code phase** of the Kinetics-to-Elecod/Lineage migration.
Phases 1-2 were architecture freeze, source-code study, register dependency mapping, and feature-parity analysis.

This Phase 3 tree is a working copy of the field-validated Kinetics gateway architecture with the first vendor-neutral extensions and the new vendor protocol catalogs/adapters added. The original Kinetics APIs, services, historian, alarm engine, security gates, staged controller, runtime monitor, and deployment structure remain in place.

## What is implemented in Phase 3

- Lineage V05 protocol catalog generator and generated catalog.
- Elecod Monet-AC V2.7.0 protocol catalog generator and generated catalog.
- FC01/FC02/FC05 support added to the existing Modbus transport layer.
- FLOAT32 word order made configurable for Lineage commissioning.
- Scale + offset codec support added for auxiliary device setpoints.
- Per-PCS TCP host/port overrides added without breaking the Kinetics RTU topology.
- Elecod >=100 ms inter-frame pacing is configurable.
- Vendor-neutral capability/state interfaces introduced.
- `LineageBmsAdapter` introduced for rack state, dynamic limits, contactors, readiness, and fault reset.
- `ElecodPcsAdapter` introduced for status, start/stop, grid mode, and kW-to-percent active-power conversion.
- Elecod power sign remains hardware-gated until low-power commissioning validates the direction.
- Lineage forced contactor operation remains capability-gated by default.
- A four-pair read-only commissioning template is provided.

## What Phase 3 deliberately does NOT claim

Phase 3 is not yet the production Elecod + Lineage site build. The following are intentionally not guessed:

1. Lineage FLOAT32 word order.
2. Lineage battery/rack current sign convention.
3. Lineage approved precharge/startup handshake.
4. Lineage forced-contactor safe sequencing for normal operation.
5. Exact auxiliary-device Unit-ID allocation beyond the V05 statement that it starts from 101.
6. Elecod positive/negative active-power direction on the actual hardware.
7. Elecod 5050/5051 final write-function behavior on the installed firmware.
8. Actual four-PCS IP/port/Unit-ID site topology.

The Phase 3 template therefore uses RFC 5737 documentation IP addresses (`192.0.2.x`) and keeps writes/control disabled.

## Phase boundaries

### Phase 3 - Actual codebase baseline (this package)
Compilable/tested source, catalogs, normalized adapters, safe config scaffolding.

### Phase 4 - Hardware read-only integration
Wire Lineage + Elecod into `GatewayService`, scheduler, asset APIs, alarm engine, history, WebSocket and diagnostics. Validate live decoding on hardware. No production writes.

### Phase 5 - Pair-control integration
Migrate `BmsPcsControlService` from Kinetics-specific point semantics to the normalized battery/PCS adapter interfaces. Enable guarded start/stop/charge/discharge after commissioning gates pass.

### Phase 6 - Full parity + production freeze
Complete safe-stop behavior, automatic four-pair operation, auxiliary assets, regression/field tests, systemd/deployment, API parity and final architecture freeze.

## Validation

Current Phase 3 automated test result:

`63 passed, 0 failed`

The 52 Kinetics baseline tests remain green, and 11 Elecod/Lineage migration tests were added.
