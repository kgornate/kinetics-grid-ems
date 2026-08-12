# v1.4 SOC-only field control

This field patch disables the need for remote monitoring/API/logging during control validation and adds a standalone controller:

```bash
tools/soc_only_controller.py
```

## Current field requirement

Solar control is intentionally excluded for now. The controller only uses SOC X and SOC Y and writes BESS ON/OFF through manual mode control.

- BESS ON = manual mode + standby
- BESS OFF = manual mode + shutdown/off

## Register mapping

| Purpose | Signal | Address | Value |
|---|---|---:|---|
| Manual mode select | `manual_auto_mode` | 10 | `0 = Manual` |
| OFF | `manual_mode_control` | 12 | `1 = Shutdown/OFF` |
| ON | `manual_mode_control` | 12 | `2 = Standby/ON` |
| SOC | `soc` | 80 | `%` |

## Decision logic

| SOC X | SOC Y | BESS X | BESS Y |
|---:|---:|---|---|
| `< 98%` | `< 98%` | ON | ON |
| `>= 98%` | `< 98%` | OFF | ON |
| `< 98%` | `>= 98%` | ON | OFF |
| `>= 98%` | `>= 98%` | ON | ON |
| `<= 75%` | `<= 75%` | ON | ON |

Solar output is ignored in this build.

## Run modes

Dry-run, one cycle, no hardware writes:

```bash
PYTHONPATH=$PWD/src python3 tools/soc_only_controller.py --once
```

Live one-cycle test:

```bash
PYTHONPATH=$PWD/src python3 tools/soc_only_controller.py --once --live --force
```

Continuous live controller:

```bash
PYTHONPATH=$PWD/src python3 tools/soc_only_controller.py --live --interval 5
```

## Disable full monitoring gateway while testing this controller

```bash
systemctl stop nb-ems-gateway.service
systemctl disable nb-ems-gateway.service
```

Then run the SOC controller manually or install the provided service.
