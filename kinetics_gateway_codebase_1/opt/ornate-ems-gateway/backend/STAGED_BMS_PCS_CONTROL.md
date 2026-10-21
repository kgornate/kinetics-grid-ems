# Kinetics Gateway V2.4 — Manual Staged BMS/PCS Control

## Purpose

This update adds a manual commissioning controller for one BMS rack and one PCS. It is designed for stage-by-stage hardware testing while the normal BMS/PCS polling, API, WebSocket, historian, authentication, Cloudflare and systemd services remain unchanged.

The first configured pair is:

- BMS Rack 1: `bms_rack_1`, BCU port 503, unit ID 2
- PCS 1: `pcs_1`, Modbus RTU slave ID 1, `/dev/ttyUSB0`, 38400 8N1

Pairs 2–4 exist in configuration but remain disabled.

## No automatic sequence

The entire staged-control code is installed in the running gateway, but there is no background automatic command loop. Every hardware-changing stage requires an explicit authenticated API request and the confirmation phrase:

`EXECUTE_STAGE_WRITE`

The full automatic sequence flag remains false.

## Confirmed register map

### BMS

| Function | Asset | Register | Encoding |
|---|---|---:|---|
| Rack N enable | BAU | `0x3005 + (rack_id - 1)` | `1=enable`, `2=disable` |
| Precharge/contact sequence request | BCU | `0x0402` | `1=start`, `0=stop/open main positive` |
| Precharge state | BCU | `0x0018` | `3=precharge success` |
| Contactor state | BCU | `0x001F` | bit0 positive, bit2 negative |
| Rack voltage | BCU | `0x0231` | S16, `0.1 V` |
| Charge current limit | BCU | `0x0225` | U16, `0.1 A` |
| Discharge current limit | BCU | `0x0226` | U16, `0.1 A` |
| Bank external fault state | BAU | `0x1001` | bitfield |
| Rack enable feedback | BAU | `0x102A` | bits 0–15 for racks 1–16 |

### PCS

| Function | Register | Encoding |
|---|---:|---|
| DC bus voltage | `0x1100` | S16, `0.1 V` |
| Actual active power | `0x110D` | S16, `0.1 kW` |
| Operating state | `0x1200` | bitfield/state word |
| Remote start/stop | `0x1400` | `0xFF00=start`, `0x00FF=stop` |
| Remote/local | `0x1402` | `0x00FF=remote`, `0xFF00=local` |
| Product mode | `0x1406` | `1=PQ mode` |
| PQ work mode | `0x1407` | `0=constant power` |
| Active power setpoint | `0x1409` | S16, `0.1 kW`; positive discharge, negative charge |

Project safety limits:

- BMS rack voltage: 1100–1500 V
- PCS DC bus voltage: 1100–1500 V
- Absolute requested power: maximum 240 kW
- Dynamic BMS power limit: `rack_voltage × allowed_current / 1000`

## Installation

Use the patch updater. It does not replace `/etc/kinetics-gateway/config.json`, networking files, systemd units or the existing BMS catalog.

After installing the patch, the gateway remains in its current read-only state.

To arm stage writes:

```bash
sh /opt/kinetics-gateway/backend/deployment/enable_staged_control_on_imx93.sh ENABLE_STAGE_WRITES
```

This only enables the API write gates. It does not issue a BMS or PCS command.

Return immediately to read-only mode:

```bash
sh /opt/kinetics-gateway/backend/deployment/disable_staged_control_on_imx93.sh
```

## Stage-by-stage commissioning commands

Run from the FRDM. The CLI uses the running gateway API and therefore does not compete with the gateway for `/dev/ttyUSB0`.

```bash
cd /opt/kinetics-gateway/backend
```

### Stage 0 — inspect capabilities and fresh status

```bash
/opt/kinetics-gateway/venv/bin/python tools/control_sequence_cli.py capabilities
/opt/kinetics-gateway/venv/bin/python tools/control_sequence_cli.py status --pair-id pair_1
```

### Stage 1 — read-only precheck

Start with a 1 kW discharge test request:

```bash
/opt/kinetics-gateway/venv/bin/python tools/control_sequence_cli.py precheck --pair-id pair_1 --direction discharge --power-kw 1
```

No hardware write occurs.

### Stage 2 — enable BMS Rack 1

```bash
/opt/kinetics-gateway/venv/bin/python tools/control_sequence_cli.py enable-rack --pair-id pair_1 --direction discharge --power-kw 1 --confirmation EXECUTE_STAGE_WRITE
```

Then inspect feedback:

```bash
/opt/kinetics-gateway/venv/bin/python tools/control_sequence_cli.py status --pair-id pair_1
```

Expected: `rack_enabled = 1`.

### Stage 3 — request BMS precharge/contact sequence

```bash
/opt/kinetics-gateway/venv/bin/python tools/control_sequence_cli.py start-precharge --pair-id pair_1 --confirmation EXECUTE_STAGE_WRITE
```

### Stage 4 — verify contactors and DC bus

```bash
/opt/kinetics-gateway/venv/bin/python tools/control_sequence_cli.py verify-ready --pair-id pair_1
```

Expected across three consecutive samples:

- Rack enabled
- Rack voltage 1100–1500 V
- Precharge state 3
- Positive and negative contactors closed
- PCS DC bus voltage 1100–1500 V
- No emergency stop/system fault

### Stage 5 — configure PCS remote PQ constant-power mode at zero power

```bash
/opt/kinetics-gateway/venv/bin/python tools/control_sequence_cli.py configure-pcs --pair-id pair_1 --confirmation EXECUTE_STAGE_WRITE
```

Writes in order:

1. `0x1402 = 0x00FF` remote mode
2. `0x1406 = 1` PQ product mode
3. `0x1407 = 0` constant-power mode
4. `0x1409 = 0.0 kW`

### Stage 6 — start PCS

```bash
/opt/kinetics-gateway/venv/bin/python tools/control_sequence_cli.py start-pcs --pair-id pair_1 --confirmation EXECUTE_STAGE_WRITE
```

The controller rejects fault-shutdown state and times out if the PCS remains stopped.

### Stage 7 — command 1 kW discharge

```bash
/opt/kinetics-gateway/venv/bin/python tools/control_sequence_cli.py set-power --pair-id pair_1 --direction discharge --power-kw 1 --confirmation EXECUTE_STAGE_WRITE
```

For charging, the controller writes a negative setpoint:

```bash
/opt/kinetics-gateway/venv/bin/python tools/control_sequence_cli.py set-power --pair-id pair_1 --direction charge --power-kw 1 --confirmation EXECUTE_STAGE_WRITE
```

### Stage 8 — verify setpoint and actual power

```bash
/opt/kinetics-gateway/venv/bin/python tools/control_sequence_cli.py verify-power --pair-id pair_1
```

### Stage 9 — safe stop

Stop PCS while leaving BMS connected:

```bash
/opt/kinetics-gateway/venv/bin/python tools/control_sequence_cli.py safe-stop --pair-id pair_1 --confirmation EXECUTE_STAGE_WRITE
```

Stop PCS, stop precharge and request Rack 1 disable:

```bash
/opt/kinetics-gateway/venv/bin/python tools/control_sequence_cli.py safe-stop --pair-id pair_1 --open-bms --confirmation EXECUTE_STAGE_WRITE
```

## API endpoints

- `GET /api/control-sequence/capabilities`
- `GET /api/control-sequence/{pair_id}/status`
- `POST /api/control-sequence/{pair_id}/precheck`
- `POST /api/control-sequence/{pair_id}/enable-rack`
- `POST /api/control-sequence/{pair_id}/start-precharge`
- `GET /api/control-sequence/{pair_id}/verify-ready`
- `POST /api/control-sequence/{pair_id}/configure-pcs`
- `POST /api/control-sequence/{pair_id}/start-pcs`
- `POST /api/control-sequence/{pair_id}/set-power`
- `GET /api/control-sequence/{pair_id}/verify-power`
- `POST /api/control-sequence/{pair_id}/safe-stop`

## Audit and recovery

Every staged write is recorded in command audit and events. The generic control endpoint remains available, but the staged API should be used for commissioning because it applies prerequisite checks and project limits.

The controller refuses writes unless all of these are true:

- Gateway mode is `control_enabled`
- BMS writes are enabled
- PCS writes are enabled
- Staged control is enabled
- The correct confirmation phrase is supplied
- The requested pair is enabled
- Stage-specific safety conditions pass
