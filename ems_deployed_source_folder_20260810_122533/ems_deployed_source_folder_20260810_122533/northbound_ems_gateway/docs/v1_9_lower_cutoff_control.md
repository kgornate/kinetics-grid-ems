# v1.9 Lower Cutoff SOC Protection

This field version adds the lower-limit use case discussed after the upper-side SOC/Solis logic.

## Confirmed command meaning

| Target | EMS command |
|---|---|
| BESS ON | `manual_auto_mode = 0`, `manual_mode_control = 2` |
| BESS OFF | `manual_auto_mode = 0`, `manual_mode_control = 1` |

## Limits

| Limit | Default | Meaning |
|---|---:|---|
| `high_limit` | 98% | Full/high SOC threshold for upper protection |
| `recovery_limit` | 75% | Upper-side post-both-high solar recovery threshold |
| `low_cutoff_limit` | 10% | Lower-side deep-discharge protection threshold |

## Lower-side final logic

Lower cutoff has the highest priority and runs before upper SOC / Solis logic.

| Case | Condition | Solar | BESS X | BESS Y | Next state |
|---|---|---|---|---|---|
| X low only | X <= low cutoff, Y > low cutoff | HOLD | OFF | ON | X_LOW_CUTOFF |
| Y low only | Y <= low cutoff, X > low cutoff | HOLD | ON | OFF | Y_LOW_CUTOFF |
| Both low | X <= low cutoff, Y <= low cutoff | HOLD | OFF | OFF | BOTH_LOW_CUTOFF_LOCKOUT |

`HOLD` means the controller does not issue a Solis command from lower cutoff logic.

## No automatic lower-side restart

When a lower cutoff state is entered, it persists until the operator clears the state file or uses `--clear-state`. This is intentional. The team concluded that restarting from a both-low shutdown may require site/DG/load/operator confirmation, so lower-side auto-recovery is not implemented.

## Existing upper-side logic remains

If no BESS is below low cutoff, the controller continues with the already implemented upper-side logic:

| Case | Condition | Solar | BESS X | BESS Y |
|---|---|---|---|---|
| Normal | X < high, Y < high | ON | ON | ON |
| X high only | X >= high, Y < high | ON | OFF | ON |
| Y high only | X < high, Y >= high | ON | ON | OFF |
| Both high | X >= high, Y >= high | OFF | ON | ON |
| Upper recovery | previous state BOTH_HIGH_SOLAR_OFF, any SOC <= recovery, trend negative | ON | ON | ON |

## Artificial validation examples

If current SOC is around X=77 and Y=72:

Y low only test:

```bash
python3 tools/soc_only_controller.py --config configs/soc_solis_field_rtu.json --once --live --force --clear-state --low-cutoff-limit 75 --high-limit 200
```

Expected:

```text
Y_LOW_CUTOFF: X ON, Y OFF, Solar HOLD
```

Both low lockout test:

```bash
python3 tools/soc_only_controller.py --config configs/soc_solis_field_rtu.json --once --live --force --clear-state --low-cutoff-limit 80 --high-limit 200
```

Expected:

```text
BOTH_LOW_CUTOFF_LOCKOUT: X OFF, Y OFF, Solar HOLD
```

Restore after lower tests requires operator intent:

```bash
python3 tools/soc_only_controller.py --config configs/soc_solis_field_rtu.json --once --live --force --clear-state --low-cutoff-limit 1 --high-limit 200 --recovery-limit 0
```

## Superseded note

The original v1.9 text said lower lockout requires manual `--clear-state`. That behavior was updated in v1.10 after field discussion with Bittu. See `docs/v1_10_lower_cutoff_recovery.md` for the current rule: low-cutoff states are held only until latest SOC recovers above `low_recovery_limit`, or immediately ignored when `low_cutoff_enabled=false`.
