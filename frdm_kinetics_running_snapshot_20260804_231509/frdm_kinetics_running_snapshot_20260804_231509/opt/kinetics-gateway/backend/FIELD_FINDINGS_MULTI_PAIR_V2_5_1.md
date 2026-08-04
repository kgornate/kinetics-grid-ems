# Kinetics Gateway V2.5.1 — Multi-Pair Field Findings

Date: 2026-07-28

## Scope

This update incorporates the field findings obtained while commissioning Pair 1 and Pair 4 and preparing Pair 2/Pair 3. It changes the normal individual-pair BMS sequence and the pair-level direction-permission gate.

## Confirmed PCS baseline

The gateway reads four PCS units over the shared Modbus RTU bus:

- PCS 1: Unit ID 1
- PCS 2: Unit ID 2
- PCS 3: Unit ID 3
- PCS 4: Unit ID 4

Healthy stopped baseline confirmed for PCS 1–4:

- Online
- Operating state `1` (stopped)
- Remote feedback active (`0x1201` bit 0)
- Setpoint `0 kW`
- Actual power `0 kW`
- `0x1202 = 0`
- `0x1210 = 0` while stopped (bit 7 becomes DC-breaker feedback when energized)
- `0x121A = 0`

PCS 1 field validation:

- `+50 kW` discharge successful
- `-60 kW` charge successful
- Zero-power and safe shutdown successful

PCS 4 field validation before this patch:

- Started from state `1`
- Progressed through state `4`, then `16`, then `32` at zero power
- DC breaker feedback closed
- DC input and DC bus matched near `1385 V`

## Confirmed individual-rack BMS path

Each rack BCU uses Unit ID 2 on its own TCP port:

- Rack 1: port 503
- Rack 2: port 504
- Rack 3: port 505
- Rack 4: port 506

For individual-pair operation, the selected rack is controlled through its own BCU register `0x0402`:

- Write `1`: start individual-rack precharge/connect sequence
- Write `0`: stop precharge/open the rack contactors
- Read `0x0018`: precharge state (`3` = success)
- Read `0x001F`: main positive and negative contactor feedback

Rack 4 field proof:

- Rack 4 BCU port 506 / Unit 2 / `0x0402 = 1` returned good readback
- `0x0018 = 3`
- Both main contactors closed
- Rack voltage `1388.7 V`
- PCS 4 input voltage `1387.6 V`
- No detailed BMS critical fault and no E-stop

## BAU indexed rack-enable registers

Normal EMS runtime must not write BAU indexed registers `0x3005–0x3008`.

The previous implementation attempted:

- Rack 1: `0x3005`
- Rack 2: `0x3006`
- Rack 3: `0x3007`
- Rack 4: `0x3008`

Rack 4 rejected both FC06 and FC16. Vendor feedback and the successful Rack 4 BCU test established that the separate BAU indexed write is not required for individual-pair runtime control.

V2.5.1 therefore:

- sends no normal-runtime write to `0x3005–0x3008`;
- retains BAU `0x102A` rack-enable feedback only as diagnostic information;
- derives `rack_enabled`/runtime readiness from selected-rack precharge state and contactor feedback for backward API/UI compatibility.

## Direction-permission finding

During the successful Rack 4 precharge/PCS startup, BAU summary register `0x1001` simultaneously asserted both `system_full` and `system_empty` while:

- detailed bank critical registers were all zero;
- detailed Rack 4 critical registers were all zero;
- Rack 4 charge current limit was `178 A`;
- Rack 4 discharge current limit was `178 A`;
- dynamic charge/discharge limit was approximately `247 kW`;
- contactors and PCS DC breaker were closed;
- PCS was ready at zero power.

For individual-pair operation, V2.5.1 treats the contradictory BAU full/empty bits as diagnostics. It enforces:

- selected-rack charge/discharge current limit;
- dynamic power limit derived from rack voltage and current limit;
- detailed bank and selected-rack critical fault words;
- E-stop;
- rack precharge/contactors;
- PCS Remote feedback, state, DC breaker, DC bus, voltage match and fault feedback.

## Revised automatic sequence

1. Configure selected PCS: stopped, Remote, PQ, constant power, `0 kW`.
2. Skip BAU indexed rack-enable write.
3. Write selected rack BCU `0x0402 = 1`.
4. Verify precharge state `3`, both contactors closed and rack voltage at PCS input.
5. Start selected PCS at `0 kW`.
6. Verify ready state, DC breaker and DC bus/input voltage match.
7. Enforce selected-rack limits and detailed faults.
8. Ramp positive kW for discharge or negative kW for charge.

## Revised safe shutdown

1. Command PCS power `0 kW` and verify actual power near zero.
2. Stop selected PCS.
3. If BMS opening is requested, write selected rack BCU `0x0402 = 0`.
4. Verify PCS stopped, precharge state `0`, contactors open and power zero.
5. Do not write BAU `0x3005–0x3008` disable values.

## Validation status

- Automated test suite: 38 passed.
- Pair 1 hardware: charge/discharge validated before this patch.
- Pair 4 hardware: individual BCU precharge and PCS zero-power startup validated before this patch.
- Pair 2 and Pair 3 PCS: healthy stopped Remote baselines confirmed.
- Pair 2/3/4 power operation after installing V2.5.1 still requires individual field validation; this document does not claim those power tests are complete.
