# v1.8 Transition-aware SOC + Solis RTU controller

This field version implements the extra sequencing agreed during the 8 July 2026 Bittu/Kunal discussion.

## Final control meanings

BESS commands remain unchanged:

| Target | EMS command |
|---|---|
| BESS ON | `manual_auto_mode = 0`, `manual_mode_control = 2` |
| BESS OFF | `manual_auto_mode = 0`, `manual_mode_control = 1` |

Reset and off-grid precaution commands remain disabled by default.

## Final SOC + solar table

| Case | SOC X | SOC Y | Solar | BESS X | BESS Y |
|---|---:|---:|---|---|---|
| Normal | `< high` | `< high` | ON | ON | ON |
| X high only | `>= high` | `< high` | ON | OFF | ON |
| Y high only | `< high` | `>= high` | ON | ON | OFF |
| Both high | `>= high` | `>= high` | OFF | ON | ON |
| Post both-high recovery | previous state `BOTH_HIGH_SOLAR_OFF`, any SOC `<= recovery`, SOC trend negative | | ON | ON | ON |

Default limits are:

```text
high = 98%
recovery = 75%
```

## v1.8 sequencing rule

The controller is now transition-aware. If one BESS was previously OFF because it crossed the high SOC limit, and later both BESS become high, the controller does not allow the second BESS to be turned OFF. Instead it follows this sequence:

```text
Previous state X_HIGH_ONLY:
1. Solar OFF
2. BESS X ON
3. BESS Y ON/reassert

Previous state Y_HIGH_ONLY:
1. Solar OFF
2. BESS Y ON
3. BESS X ON/reassert
```

This prevents a transient condition where both BESS are OFF or where both need to start together. The delay between actions is configurable:

```text
inter_device_command_delay_sec = 2.0
```

## Main configs

Solis enabled:

```text
configs/soc_solis_field_rtu.json
```

BESS only, no Solis:

```text
configs/soc_only_field_no_solar.json
```

## Main commands

Dry-run once:

```bash
python3 tools/soc_only_controller.py --config configs/soc_solis_field_rtu.json --once --clear-state
```

Live once:

```bash
python3 tools/soc_only_controller.py --config configs/soc_solis_field_rtu.json --once --live --force --clear-state
```

Automatic live:

```bash
python3 tools/soc_only_controller.py --config configs/soc_solis_field_rtu.json --live --force
```

## Transition test using artificial high limits

Assume X SOC is around 77 and Y SOC is around 72.

Create one-high state:

```bash
python3 tools/soc_only_controller.py --config configs/soc_solis_field_rtu.json --once --live --force --clear-state --high-limit 75 --recovery-limit 0
```

Expected:

```text
X_HIGH_ONLY: Solar ON, X OFF, Y ON
```

Without clearing state, trigger both-high state:

```bash
python3 tools/soc_only_controller.py --config configs/soc_solis_field_rtu.json --once --live --force --high-limit 72 --recovery-limit 0
```

Expected action order:

```text
1. Solis OFF
2. X ON
3. Y ON
```

The expected final state is:

```text
BOTH_HIGH_SOLAR_OFF: Solar OFF, X ON, Y ON
```
