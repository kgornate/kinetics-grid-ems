# Elecod + Lineage Field-Validation Gates

The gateway code is intentionally complete before the physical BESS arrives. The supplied protocol documents do not fully define several runtime behaviours, so production hardware control is positively locked until these are verified rather than guessed.

## Lineage BMS

1. **Register addressing / offset** - compare known system/rack values against the V05 decimal addresses.
2. **FLOAT32 word order** - V05 specifies FLOAT but not 32-bit word order.
3. **Current sign** - confirm charge/discharge polarity for system and rack current.
4. **Automatic precharge/readiness sequence** - V05 exposes main-contactor feedback and precharge faults but no normal EMS precharge command/success point. Confirm how the BMS should be brought from idle to DC-path-ready state.
5. **Warn policy** - default gateway policy blocks charge/discharge in `0xCCCC Warn` until the vendor/site safety policy is explicitly approved.
6. **Forced disconnect sequence** - only required if EMS-forced positive/negative contactor opening is intentionally enabled. Default is disabled.
7. **Auxiliary Unit-ID allocation** - V05 states auxiliary addresses start from 101 but the final chiller/temp-humidity/water/dehumidifier allocation must be supplied for the site.

## Elecod PCS

1. **Register addressing / offset** - verify telemetry and status against V2.7.0.
2. **Active-power sign** - the register map strongly indicates positive = discharge and negative = charge; confirm with low-power commissioning.
3. **5050/5051 write function and start/stop behaviour** - the release history and examples have FC05/FC06 wording inconsistency. The driver uses FC06 by default.
4. **2057 readiness/status behaviour** - confirm run/fault/DC relay/AC relay/precharge bits through startup and stop.
5. **DC input/DC bus voltage behaviour while stopped** - confirm which values are valid before start for voltage matching.
6. **Actual site TCP topology** - four IPs, shared endpoint with Unit IDs, or vendor master aggregation must be reflected only in configuration.

## Positive software gates

Real Lineage + Elecod pair writes require the normal Kinetics safety gates plus explicit validation booleans in configuration. Mock/SIL mode bypasses field-validation booleans only so the complete software state machine can be tested without hardware.

Never mark a gate as validated solely to make a command execute.
