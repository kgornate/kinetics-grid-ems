# Kinetics Gateway: Four-PCS Modbus RTU Integration

## Safety state

The supplied RTU template keeps `pcs.enabled=false` and `pcs.write_enabled=false`.
Do not enable PCS polling until the vendor confirms the serial parameters and slave IDs.
Do not enable writes until register data types, scaling, write functions, command values and the safe operating sequence are confirmed.

## Confirmed architecture

- BMS remains unchanged on Modbus TCP through `eth1`.
- Four PCS units share one Modbus RTU / RS485 bus.
- Each PCS uses the same 230-register map and must have a unique Modbus slave ID.
- PCS devices are polled sequentially through one shared serial client and lock.

## Pending vendor parameters

- RS485 device/adapter identity
- Baud rate
- Data bits
- Parity
- Stop bits
- Slave IDs for PCS 1-4
- Whether sheet address `0x0001` is sent as PDU address `0x0001` or `0x0000`
- Register signedness, widths, scaling, units and word order
- Writable registers, FC06/FC16 selection and valid command values

## New API fields and endpoints

Backward compatibility is retained:

- `GET /api/pcs` continues to return the primary `pcs_1` object.
- `snapshot["pcs"]` and compact WebSocket `pcs` remain available.

New multi-PCS access:

- `GET /api/pcs/all`
- `GET /api/pcs/pcs_1` through `GET /api/pcs/pcs_4`
- `snapshot["pcs_devices"]`
- compact WebSocket `pcs_devices`

## Configuration template

Use `configs/kinetics_hardware_bms_4pcs_rtu_template.json` as the staging template.
The existing `/etc/kinetics-gateway/config.json`, BMS code, network service and systemd service are intentionally not replaced.

## Stable serial device

Create `/dev/pcs_rs485` with the provided udev rule example. Do not permanently configure `/dev/ttyUSB0`, because enumeration can change after reboot.

## Commissioning sequence

1. Identify the RS485 adapter and create `/dev/pcs_rs485`.
2. Confirm A/B/GND wiring, termination and biasing.
3. Confirm serial parameters and unique slave IDs.
4. Install `pyserial` in the existing gateway virtual environment.
5. Run `tools/pcs_rtu_probe.py` with writes disabled.
6. Confirm all four slaves separately.
7. Copy only the verified PCS block into `/etc/kinetics-gateway/config.json`.
8. Keep `mode=read_only` and `write_enabled=false` during extraction validation.
9. Enable PCS writes only after vendor command documentation and system interlocks are validated.
