# v1.10 Lower Cutoff Recovery / Stale-State Fix

This version updates the lower-limit logic based on the Bittu field discussion on 2026-07-08.

## Problem found in field testing

The previous v1.9 lower-cutoff state was permanently sticky. Once the state file contained:

```text
state = X_LOW_CUTOFF
low_cutoff_reason = X_SOC_BELOW_LOW_LIMIT
```

then later upper-limit operation could be blocked even if the latest SOC was no longer low. This is what caused the controller to keep commanding `X = OFF` while current SOC was already high.

## New rule

Lower cutoff is now optional and config-gated:

```json
"low_cutoff_enabled": false
```

When lower cutoff is enabled, the low state is still protective, but it is no longer a permanent blocker. The gateway continuously reads latest SOC. If a field operator manually inspects/turns the BESS ON and the latest SOC is above the configured recovery threshold, the gateway clears the stale low-cutoff state and resumes normal/upper-limit logic.

## Parameters

| Parameter | Meaning |
|---|---|
| `low_cutoff_enabled` | Enables/disables lower SOC protection |
| `low_cutoff_limit` | SOC at/below which lower cutoff is triggered |
| `low_recovery_limit` | SOC at/above which a latched low-cutoff state can be cleared |

For exact Bittu behavior, use:

```json
"low_cutoff_limit": 10.0,
"low_recovery_limit": 10.0
```

For more hysteresis against SOC bounce, use something like:

```json
"low_cutoff_limit": 10.0,
"low_recovery_limit": 12.0
```

## Updated state behavior

| Previous state | Latest SOC condition | New behavior |
|---|---|---|
| `X_LOW_CUTOFF` | X still below recovery | Keep X OFF, Y ON |
| `X_LOW_CUTOFF` | X recovered above recovery | Clear low state and run upper/normal logic |
| `Y_LOW_CUTOFF` | Y still below recovery | Keep X ON, Y OFF |
| `Y_LOW_CUTOFF` | Y recovered above recovery | Clear low state and run upper/normal logic |
| `BOTH_LOW_CUTOFF_LOCKOUT` | either BESS still below recovery | Keep both OFF |
| `BOTH_LOW_CUTOFF_LOCKOUT` | both BESS recovered above recovery | Clear low state and run upper/normal logic |
| any low state | `low_cutoff_enabled = false` | Clear stale low state and run upper/normal logic |

## Current field configs

For the current upper-limit and Solis validation work, lower cutoff is disabled in both field configs to avoid blocking upper SOC behavior:

- `configs/soc_only_field_no_solar.json`
- `configs/soc_solis_field_rtu.json`

Lower cutoff can be enabled later by setting:

```json
"low_cutoff_enabled": true,
"low_cutoff_limit": 10.0,
"low_recovery_limit": 10.0
```

or from CLI:

```bash
python3 tools/soc_only_controller.py \
  --config configs/soc_solis_field_rtu.json \
  --once \
  --live \
  --force \
  --low-cutoff-enable \
  --low-cutoff-limit 10 \
  --low-recovery-limit 10
```

## Safety note

Lower cutoff still has higher priority than upper SOC logic when enabled. The change only adds a proper recovery/exit path so stale lower-limit state cannot permanently block upper-limit control after SOC has recovered.
