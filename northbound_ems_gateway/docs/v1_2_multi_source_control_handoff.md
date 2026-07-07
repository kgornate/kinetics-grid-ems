# NorthBound EMS Gateway v1.2 - Multi-Source Control Handoff

## Field architecture

The gateway controls two independent Chinese EMS/BESS units over `eth1` through the same Modbus TCP protocol map.

| Source ID | Display Name | IP | Port | Unit ID |
| --- | --- | --- | --- | --- |
| `external_ems_1` | Chinese EMS 1 | `192.168.100.151` | `502` | `1` |
| `external_ems_2` | Chinese EMS 2 | `192.168.100.153` | `502` | `1` |

The protocol source is `data/protocol_sources/unity261pv_modbus_north_en_v1.xlsx` and the generated base register map is `data/register_maps/unity261pv_modbus_north_v1.json`.

## Key register mapping

| Address | Signal name | Purpose |
| ---: | --- | --- |
| `42` | `manual_charge_value_setting` | Manual charge power command in kW |
| `44` | `manual_discharge_value_setting` | Manual discharge power command in kW |
| `164` | `on_off_grid_switching` | Write `1` for grid-tied/on-grid, write `2` for off-grid |
| `180` | `pcs_on_off_grid_status` | Read `0` for off-grid, `1` for on-grid |
| `346` | `phase_a_voltage` | Phase A voltage for off-grid stabilization |
| `348` | `phase_b_voltage` | Phase B voltage for off-grid stabilization |
| `350` | `phase_c_voltage` | Phase C voltage for off-grid stabilization |

## New APIs

All APIs except login require Bearer token. Command/control APIs require `internal_admin`.

### Source APIs

```text
GET /api/sources
GET /api/sources/summary
GET /api/sources/{source_id}
GET /api/sources/{source_id}/assets
GET /api/sources/{source_id}/telemetry
```

### Source-aware raw command APIs

```text
GET  /api/commands/ems/registers?source_id=external_ems_1
GET  /api/commands/ems/registers?source_id=external_ems_2
POST /api/commands/ems/write
POST /api/commands/ems/batch
```

Example raw write:

```json
{
  "source_id": "external_ems_1",
  "signal_name": "on_off_grid_switching",
  "value": 1,
  "readback": true
}
```

### High-level control APIs

```text
POST /api/control/sources/{source_id}/grid-mode
POST /api/control/sources/{source_id}/charge
POST /api/control/sources/{source_id}/discharge
POST /api/control/sources/{source_id}/standby
POST /api/control/site/grid-mode
POST /api/control/site/power
POST /api/control/site/standby
```

Grid-tied example:

```json
{
  "target_mode": "grid_tied",
  "readback": true,
  "timeout_sec": 60
}
```

Off-grid site-level sequence example:

```json
{
  "target_mode": "off_grid",
  "source_order": ["external_ems_1", "external_ems_2"],
  "wait_for_voltage_stable": true,
  "readback": true
}
```

The site-level off-grid command is sequential: EMS 1 is switched first, register `180` is checked, voltage stability is checked using registers `346`, `348`, and `350`, and only then EMS 2 is switched.

## Command-line test flow

Start gateway on hardware:

```bash
cd /root/northbound_ems_gateway
python3 -m nb_ems_gateway.main --config configs/development.json
```

Login and list sources:

```bash
python3 tools/control_cli.py --base-url http://127.0.0.1:8000 sources
```

Switch one EMS to grid-tied:

```bash
python3 tools/control_cli.py --base-url http://127.0.0.1:8000 grid-mode external_ems_1 grid_tied
```

Switch both to off-grid sequentially:

```bash
python3 tools/control_cli.py --base-url http://127.0.0.1:8000 site-grid-mode off_grid --order external_ems_1 external_ems_2
```

Charge/discharge examples:

```bash
python3 tools/control_cli.py --base-url http://127.0.0.1:8000 charge external_ems_1 50
python3 tools/control_cli.py --base-url http://127.0.0.1:8000 discharge external_ems_2 50
python3 tools/control_cli.py --base-url http://127.0.0.1:8000 site-power charge 100
python3 tools/control_cli.py --base-url http://127.0.0.1:8000 site-power discharge 100
python3 tools/control_cli.py --base-url http://127.0.0.1:8000 site-standby
```

Default CLI credentials are `internal` / `Internal@123`.
