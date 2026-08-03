# Control Sequence API V2.5.0

All endpoints require an authenticated internal-role token.

## Capabilities

`GET /api/control-sequence/capabilities`

Returns enabled pairs, confirmation phrases, configured safety limits and the validated sequence.

## Live status

`GET /api/control-sequence/pair_1/status?fresh=true`

Important response sections:

- `summary`: rack, BMS, contactor, PCS, power and limit values
- `blockers`: E-stop, documented critical faults and direction prohibitions
- `workflow`: derived system state and completed readiness steps
- `runtime`: active automatic-run ID, stage, step list, status and errors
- `write_gates`: active control configuration

## Automatic startup and power command

`POST /api/control-sequence/pair_1/automatic-start`

```json
{
  "direction": "discharge",
  "power_kw": 50,
  "ramp_step_kw": 10,
  "ramp_interval_seconds": 1,
  "confirmation": "EXECUTE_AUTOMATIC_SEQUENCE"
}
```

The gateway performs PCS configuration, rack enable, BMS precharge, PCS startup, power precheck, ramp and power tracking. Any failure triggers a complete safe-stop attempt.

## Commissioning next step

`POST /api/control-sequence/pair_1/next-step`

```json
{
  "direction": "charge",
  "power_kw": 60,
  "confirmation": "EXECUTE_STAGE_WRITE"
}
```

The gateway reads current hardware feedback and executes only the next valid stage.

## Direct power command

`POST /api/control-sequence/pair_1/set-power`

```json
{
  "direction": "charge",
  "power_kw": 60,
  "confirmation": "EXECUTE_STAGE_WRITE"
}
```

The API accepts unsigned magnitude plus direction. The gateway writes `-60 kW` for charge and `+60 kW` for discharge only after readiness and BMS-limit checks pass.

## Zero power

`POST /api/control-sequence/pair_1/zero-power`

```json
{"confirmation":"EXECUTE_STAGE_WRITE"}
```

## Complete safe shutdown

`POST /api/control-sequence/pair_1/safe-stop`

```json
{
  "open_bms": true,
  "confirmation": "EXECUTE_STAGE_WRITE"
}
```

## Abort automatic sequence

`POST /api/control-sequence/pair_1/abort`

```json
{
  "open_bms": true,
  "confirmation": "EXECUTE_STAGE_WRITE"
}
```

Abort sets the run's cancellation flag and executes safe shutdown.
