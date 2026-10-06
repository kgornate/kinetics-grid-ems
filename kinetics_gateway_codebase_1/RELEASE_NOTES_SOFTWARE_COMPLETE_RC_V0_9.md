# Release Notes - Software-Complete RC v0.9

## Added

- Vendor-neutral Lineage BMS + Elecod PCS four-pair control service.
- Factory-based controller selection preserving the original Kinetics controller.
- Complete automatic charge/discharge path with dynamic Lineage rack/system power limiting.
- Elecod kW-to-vendor-percentage conversion behind the normalized adapter.
- Runtime power tracking, permission/contactor/fault monitoring and safe-stop.
- Software-in-loop four-pair digital twin.
- Explicit hardware field-validation flags and positive write lockout.
- Platform/commissioning readiness APIs.
- Normalized BAMS fire/safety/container I/O view without overstating it as a full fire-controller protocol.
- Full-source deployment and SIL validation scripts.

## Safety changes

- Generic raw-point API cannot write critical Elecod power/start/mode points.
- Generic raw-point API cannot force Lineage rack contactors.
- Real Lineage + Elecod writes require confirmed addressing, FLOAT/current/precharge and Elecod start/status validation gates.
- Lineage `Warn` blocks charge/discharge by default.
- Forced Lineage battery disconnect remains disabled by default and needs its own validated sequence.

## Not claimed

This release has not been field-validated against the new physical BESS. Protocol behaviours explicitly missing from the source documents remain commissioning gates and are documented in `docs/FIELD_VALIDATION_GATES.md`.
