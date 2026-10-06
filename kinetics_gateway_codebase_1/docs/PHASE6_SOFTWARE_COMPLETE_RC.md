# Phase 6 - Software-Complete Release Candidate v0.9

This release is the pre-hardware, software-complete candidate for the Ornate EMS Gateway platform.

## Meaning of "software complete"

All intended Lineage + Elecod gateway paths are implemented in the same source tree as the retained Kinetics baseline:

- protocol catalogs and transports
- system/rack/cell/PCS telemetry
- alarms and normalized safety summary
- historian and command/event audit
- normalized asset/pair views
- staged pair control
- automatic four-pair charge/discharge sequence
- dynamic BMS power limiting
- power ramp and tracking
- runtime safety monitoring
- abort, safe-stop and safe-stop-all
- API/WebSocket integration
- simulation/digital twin and regression suite
- deployment templates and positive commissioning gates

## Meaning of "not yet production frozen"

No claim is made that the unresolved protocol behaviours have been validated on the physical BESS. Field validation is required before enabling real Lineage/Elecod writes. The release therefore reports `software_complete_field_validation_pending` through `/api/platform/readiness`.

## Release progression

```text
v0.9 software-complete RC
    -> read-only hardware commissioning
    -> low-power staged control commissioning
    -> four-pair automatic/control validation
    -> fault/safe-stop validation
    -> v1.0 production architecture freeze
```

No architecture rewrite is expected during that progression. Field findings should update configuration, vendor adapters, capability policy or tests unless the physical system reveals a genuinely missing system requirement.
