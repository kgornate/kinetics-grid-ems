# Kinetics Gateway V2.5.0 — Field-Validated BMS/PCS Control Sequence

## Validated hardware sequence

The following sequence was validated on 2026-07-28 with BMS Rack 1 and PCS 1:

1. Keep PCS stopped, Remote, PQ mode, constant-power mode and 0 kW.
2. Enable Rack 1 through BAU `0x3005 = 1` and verify Rack 1 bit in `0x102A`.
3. Leave BMS insulation command `0x0401 = 0`; the BMS handles insulation internally.
4. Start BMS precharge with `0x0402 = 1`.
5. Verify precharge state `0x0018 = 3`, positive and negative contactors closed, and rack voltage present at PCS input.
6. Start PCS with `0x1400 = 0xFF00` while setpoint remains 0 kW.
7. Observe PCS states through soft-start/self-test/standby/running, verify internal DC breaker closed and DC bus matched to battery input.
8. Apply signed power within BMS limits:
   - positive kW = discharge
   - negative kW = charge
9. Runtime monitoring continuously checks BMS direction permission, dynamic power limits, contactors, PCS DC breaker, critical faults and communication health.

Validated operating tests:

- `+50 kW` discharge tracked approximately 49.4–50.0 kW.
- `-60 kW` charge command was accepted and validated in the field.

## Safe shutdown

1. Command 0 kW.
2. Verify actual power returns near zero.
3. Stop PCS with `0x1400 = 0x00FF`.
4. Reset BMS precharge with `0x0402 = 0`.
5. Disable Rack 1 with `0x3005 = 2`.
6. Verify rack feedback disabled, precharge state 0 and both main contactors open.

Residual PCS input/DC-link voltage can decay after the contactors open. Operational shutdown success is based on zero power, PCS stopped, rack disabled and contactors open. Physical maintenance must follow the PCS vendor's isolation and discharge procedure.

## Operator APIs

- `GET /api/control-sequence/capabilities`
- `GET /api/control-sequence/{pair_id}/status?fresh=true`
- `POST /api/control-sequence/{pair_id}/automatic-start`
- `POST /api/control-sequence/{pair_id}/next-step`
- `POST /api/control-sequence/{pair_id}/configure-pcs`
- `POST /api/control-sequence/{pair_id}/enable-rack`
- `POST /api/control-sequence/{pair_id}/start-precharge`
- `POST /api/control-sequence/{pair_id}/start-pcs`
- `POST /api/control-sequence/{pair_id}/set-power`
- `POST /api/control-sequence/{pair_id}/zero-power`
- `POST /api/control-sequence/{pair_id}/safe-stop`
- `POST /api/control-sequence/{pair_id}/abort`

## Automatic request example

```json
{
  "direction": "charge",
  "power_kw": 60,
  "ramp_step_kw": 10,
  "ramp_interval_seconds": 1,
  "confirmation": "EXECUTE_AUTOMATIC_SEQUENCE"
}
```

The endpoint returns `202 Accepted` with a run ID. Poll the status endpoint to show current stage, individual step results, faults and final state.

## Safety gates

Automatic execution requires all of the following:

- `mode = control_enabled`
- `bms.write_enabled = true`
- `pcs.write_enabled = true`
- `control_sequence.enabled = true`
- `control_sequence.allow_full_automatic_sequence = true`
- confirmation phrase `EXECUTE_AUTOMATIC_SEQUENCE`

Commissioning-stage writes use `EXECUTE_STAGE_WRITE`.

The stale BMS summary bit in `0x1001` remains diagnostic. Energising commands use documented detailed fault registers `0x1004`, `0x1007`, `0x100C`, `0x100D`, `0x0011`, `0x0012` and `0x0015` as hard blockers.
