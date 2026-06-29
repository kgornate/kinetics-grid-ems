# Read-Only Safety Policy

Version 1 is a monitoring-only gateway.

The software must not:

- write Modbus registers
- expose command endpoints
- reset faults
- start/stop PCS or BMS
- change charge/discharge mode
- change remote schedules
- change grid/off-grid settings
- modify protection or insulation thresholds

The Modbus client intentionally blocks write methods with `ModbusWriteBlockedError`.
