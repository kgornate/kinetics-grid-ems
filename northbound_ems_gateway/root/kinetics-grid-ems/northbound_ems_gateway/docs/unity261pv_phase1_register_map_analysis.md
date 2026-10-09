# Phase 1 - Unity261PV Register Map Integration Analysis

## Input files

- New Excel: `Unity261PV-modbus-north-EN (1).xlsx`
- Copied protocol source: `data/protocol_sources/unity261pv_modbus_north_en_v1.xlsx`
- Generated register map: `data/register_maps/unity261pv_modbus_north_v1.json`

## Key result

The new Unity261PV Excel is a **single-device protocol map**. Because both field EMS devices use the same register table and same Modbus TCP port, the gateway should instantiate this one base map twice at runtime: once for `external_ems_1` and once for `external_ems_2`.

## Old vs new summary

| Item | Old EUR261 map | New Unity261PV map |
|---|---:|---:|
| Port | 515 | 502 |
| Unit ID | 1 | 1 |
| Point count | 1421 | 1422 |
| Address range | 0-2840 | 0-2842 |
| Writable point count | 439 | 92 |

## New map asset counts

| Asset ID | Count |
|---|---:|
| `ems_system` | 93 |
| `pcs_1` | 270 |
| `bms_1` | 761 |
| `io_module` | 21 |
| `liquid_cooling` | 113 |
| `fire_protection` | 23 |
| `dehumidifier` | 16 |
| `remote_control` | 56 |
| `utility_meter` | 69 |

## New map entity counts

| Entity | Count |
|---|---:|
| EMS System Parameters | 93 |
| PCS1 | 60 |
| PCS Communication Parameters 1 | 210 |
| BMS Communication Parameters 1 | 761 |
| IO | 21 |
| Liquid Cooling Communication Parameters | 113 |
| Fire Protection Communication Parameters | 23 |
| Dehumidifier Communication Parameters | 16 |
| Remote Control | 56 |
| Grid Meter Communication Parameters | 69 |

## Vendor control / feedback registers found

| Address | Signal name | Point name | Unit | R/W | Description |
|---:|---|---|---|---:|---|
| 42 | `manual_charge_value_setting` | Manual Charge Value Setting | kW | 1 |  |
| 44 | `manual_discharge_value_setting` | Manual Discharge Value Setting | kW | 1 |  |
| 164 | `on_off_grid_switching` | On/Off-Grid Switching |  | 1 | 0,Completed;1,On-Grid;2,Off-Grid |
| 180 | `pcs_on_off_grid_status` | PCS On/Off-Grid Status |  | 1 | 0,Off-Grid;1,On-Grid |
| 346 | `phase_a_voltage` | Phase A Voltage | V | 0 |  |
| 348 | `phase_b_voltage` | Phase B Voltage | V | 0 |  |
| 350 | `phase_c_voltage` | Phase C Voltage | V | 0 |  |

## Phase 1 conclusion

Phase 1 is complete: the new Excel has been imported into the backend package as a versioned protocol source, and a new base JSON register map has been generated. The next phase is backend multi-source configuration so this same base register map can be applied to both `192.168.100.151:502` and `192.168.100.153:502`.