# NorthBound Asset Field Matrix

Total decoded register points: **1421**

| Asset ID | Display Name | Fields | Main Categories | Example Important Fields |
| --- | --- | ---: | --- | --- |
| `bms_1` | BMS 1 | 761 | voltage(375), temperature(275), current(36), insulation(19), fault_alarm(15) | SOC Too Low (Level 3); Rack SOC Too Low Level 3 Alarm Threshold (Warning); Pre-Power-On Phase; Total Voltage Difference Too Large; Current Too High; Cell Temperature Too High; Insulation Too Low; Contactor Fault |
| `pcs_1` | PCS 1 | 269 | fault_alarm(57), general(43), power(39), status(37), current(31) | Charge SOC Setpoint (%); Discharge SOC Setpoint (%); Rated Power; BMS Total Voltage; BMS Max Available Charge Current; Grid Frequency; Heatsink Temperature; Insulation Resistance Value |
| `liquid_cooling` | Liquid Cooling | 113 | fault_alarm(52), temperature(36), general(13), status(6), power(3) | Power Supply Overvoltage Alarm; Power Supply Undervoltage Alarm; System A Compressor Frequency Abnormal; Water Temp Control Target; Working Mode; Monitoring Mode; Outlet High-Pressure Alarm Value; Inlet Low-Pressure Alarm Value |
| `ems_system` | EMS System | 93 | status(33), general(24), power(12), soc_soh(12), fault_alarm(7) | Charge SOC Setpoint (%); Discharge SOC Setpoint (%); Master Charge Power Command; Utility Current Total Power; Battery Precharge Control; Available Quantity; Remote Mode; System Fault |
| `utility_meter` | Utility Meter | 69 | power(22), voltage(18), current(16), temperature(5), energy(3) | A-Phase Active Power; A-Phase Voltage; A-Phase Current; Frequency; Reserved Internal Temperature; Comm Status; DO1 Alarm Output; Overvoltage Alarm |
| `remote_control` | Remote Control | 56 | status(43), power(10), soc_soh(3) | Remote Mode SOC Limit Enable; Remote Mode Charge Cutoff SOC; Period 1 Active Power; Remote Mode; Remote Control Mode; System Fault Reset |
| `fire_protection` | Fire Protection | 23 | fault_alarm(16), temperature(3), status(2), current(2) | Fan Damper Control Module - Fire Alarm; Fault - Temperature; Comm Status; Fault - CO; Fault - Start |
| `io_module` | I/O Module | 21 | io(12), fault_alarm(4), status(3), general(2) | Comm Status; Water Ingress Alarm; Fire Protection Sprinkler |
| `dehumidifier` | Dehumidifier | 16 | humidity(5), status(5), temperature(4), current(2) | Current Temperature; Temperature Setpoint; Working Mode; Humidity Control Mode; Alarm Status |

## Category counts per asset

### BMS 1 (`bms_1`)

| Category | Count |
| --- | ---: |
| voltage | 375 |
| temperature | 275 |
| current | 36 |
| insulation | 19 |
| fault_alarm | 15 |
| general | 11 |
| soc_soh | 10 |
| status | 10 |
| power | 5 |
| energy | 4 |
| io | 1 |

### Dehumidifier (`dehumidifier`)

| Category | Count |
| --- | ---: |
| humidity | 5 |
| status | 5 |
| temperature | 4 |
| current | 2 |

### EMS System (`ems_system`)

| Category | Count |
| --- | ---: |
| status | 33 |
| general | 24 |
| power | 12 |
| soc_soh | 12 |
| fault_alarm | 7 |
| io | 3 |
| current | 2 |

### Fire Protection (`fire_protection`)

| Category | Count |
| --- | ---: |
| fault_alarm | 16 |
| temperature | 3 |
| status | 2 |
| current | 2 |

### I/O Module (`io_module`)

| Category | Count |
| --- | ---: |
| io | 12 |
| fault_alarm | 4 |
| status | 3 |
| general | 2 |

### Liquid Cooling (`liquid_cooling`)

| Category | Count |
| --- | ---: |
| fault_alarm | 52 |
| temperature | 36 |
| general | 13 |
| status | 6 |
| power | 3 |
| voltage | 2 |
| io | 1 |

### PCS 1 (`pcs_1`)

| Category | Count |
| --- | ---: |
| fault_alarm | 57 |
| general | 43 |
| power | 39 |
| status | 37 |
| current | 31 |
| voltage | 28 |
| temperature | 15 |
| soc_soh | 7 |
| energy | 6 |
| insulation | 4 |
| io | 2 |

### Remote Control (`remote_control`)

| Category | Count |
| --- | ---: |
| status | 43 |
| power | 10 |
| soc_soh | 3 |

### Utility Meter (`utility_meter`)

| Category | Count |
| --- | ---: |
| power | 22 |
| voltage | 18 |
| current | 16 |
| temperature | 5 |
| energy | 3 |
| fault_alarm | 3 |
| status | 1 |
| general | 1 |
