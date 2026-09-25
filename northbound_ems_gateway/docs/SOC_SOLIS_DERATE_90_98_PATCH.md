# SOC + Solis 90%/98% Derating Patch

Baseline: gateway_complete_code_20260910T082622Z
Controller version: v1.14_soc_solar_derate_90_98

## Approved behavior

- Both BESS SOC <= 90% or only one BESS > 90%: Solis normal power setting.
- Both BESS SOC > 90% and not both >= 98%: Solis stays ON and is derated to 20 kW.
- Both BESS SOC >= 98%: existing Solis OFF latch/recovery logic is retained.
- A single BESS >= 98% keeps the existing protection behavior (that BESS OFF, other BESS ON). Solar is derated only if both SOC values are > 90%.
- Existing post-both-high recovery threshold/trend behavior is unchanged.

## Field-validated Solis power control

- FC03/FC06 holding register 3051: active-power percentage setpoint.
- 10000 = 100%; field baseline was 11000 = 110%.
- Validated inverter active-power base: 100 kW.
- 20 kW target => 20% => raw 2000.
- Register 3069 was observed as 0xAA (active-power control enabled). The controller checks this value but does not rewrite it automatically.
- Verification chain used in field:
  - 3051 readback = 2000
  - FC04 3049 feedback = 2000
  - FC04 3044-3045 limit feedback = 20000 W
  - FC04 3004-3005 actual power stabilized around 20 kW
  - FC04 3089 = 0xAA and 3094 changed while limiting was active

## New runtime settings

- derate_soc_limit = 90.0
- derate_power_kw = 20.0
- high_limit = 98.0
- recovery_limit = 75.0

Existing v1.13 control_settings.json files are backward compatible: missing derate settings are filled with 90% / 20 kW defaults.

## Solis config additions

- rated_power_kw = 100.0
- normal_power_percent = 110.0

The controller restores register 3051 to the configured normal percentage whenever solar should return to normal operation. During a derated state it derives the register 3051 raw value from derate_power_kw and rated_power_kw.
