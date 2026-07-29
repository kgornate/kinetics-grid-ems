# Kinetics Flutter Dashboard V2.6 — BESS Control Sequence

## New internal Control screen

The dashboard now provides a dedicated field-validated BMS Rack ↔ PCS control page for internal users.

Features:

- live system state and safety-gate indicators
- rack voltage, PCS input voltage, PCS DC-bus voltage and actual/setpoint power
- BMS charge/discharge current and derived power limits
- contactor, precharge, DC-breaker, fault and prohibition status
- automatic startup with direction, target power, ramp step and ramp interval
- step-by-step commissioning using **Execute next step**
- direct power command only when gateway readiness is true
- zero-power command
- complete safe shutdown
- automatic-sequence abort
- expandable latest raw gateway response
- live stepper for automatic progress or validated readiness

## Security

The Control destination is visible only to users whose JWT role is `internal`. Customer accounts remain read-only.

## Backend dependency

Use Kinetics Gateway backend V2.5.0 or newer. Automatic mode remains disabled in the UI until the backend capability reports `full_automatic_sequence_allowed = true`.
