# Kinetics Flutter Dashboard V3.0.0

- Independent command busy state for Pair 1-4; one pair no longer blocks another.
- Cache-only `/api/control-sequence/status/all` overview polling every two seconds.
- Explicit selected-pair live refresh only on operator request, preventing fieldbus contention.
- Canonical top-level control status parsing; no recursive/nested workflow snapshot selection.
- Pair cards show setpoint, actual power, PCS/precharge state, source and stale status.
- Aggregate plant setpoint and actual power.
- Pair-specific automatic ramp and direct set-power controls for charge/discharge.
- Pair safe shutdown and sequential `Safe stop all pairs`.
- Longer manual-stage timeout to accommodate verified PCS start without false UI failure.
- `bms_banks` and all `pcs_devices` are parsed without exposing pair BAUs as environment assets.
- Fixed-size pair/state collections and gateway-side bounded event buffers avoid unbounded memory growth.
