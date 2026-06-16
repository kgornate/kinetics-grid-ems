# Operator Telemetry API

The gateway exposes full engineering telemetry and filtered operator telemetry.

## Why operator telemetry exists

Full telemetry includes values needed for diagnostics and support, such as raw Modbus registers, storage logger paths, and internal debug fields. These are useful for engineering, but they add noise in an operator dashboard grid.

Operator telemetry removes noisy fields while preserving operational values such as temperatures, pressures, power, SOC, status, alarms, faults, and command-relevant values.

## Existing full telemetry endpoints

These remain unchanged:

```text
GET /api/telemetry/latest
GET /api/assets/{asset_id}/telemetry/latest
GET /api/assets/{asset_id}/telemetry/keys
GET /api/stream/telemetry
```

Use these for engineering/debug tools.

## New operator telemetry endpoints

Use these for dashboard grids:

```text
GET /api/telemetry/operator
GET /api/telemetry/latest?view=operator
GET /api/assets/{asset_id}/telemetry/operator
GET /api/assets/{asset_id}/telemetry/latest?view=operator
GET /api/assets/{asset_id}/telemetry/keys?view=operator
GET /api/stream/telemetry?view=operator
```

Example URLs:

```text
http://192.168.88.16:8000/api/telemetry/operator
http://192.168.88.16:8000/api/assets/chiller_1/telemetry/operator
http://192.168.88.16:8000/api/assets/pcs_1/telemetry/operator
http://192.168.88.16:8000/api/assets/bms_1/telemetry/operator
```

## Fields filtered from operator view

The filter removes fields such as:

```text
storage_logger
raw_telemetry_registers
raw_registers
settings_registers_200_to_208
register_map
debug
internal
raw_*
*_raw
*_registers
registers_*
fault_binary
fault_active_bits
```

The filter keeps operator-useful fields such as:

```text
communication_status
fault_code
fault_active
fault_description
control_mode
set_temperature
outlet_water_temp
return_water_temp
outlet_water_pressure
return_water_pressure
ambient_temp
SOC / SOH / pack voltage / pack current
PCS power / voltage / current / status / alarms
```

## Integration recommendation

For operator dashboard telemetry grids, use operator endpoints. Keep existing full endpoints available for diagnostics or a separate engineering/debug panel.
