# PCS Modbus RTU HMI-map validation

Validated on 2026-07-27 against PCS slave ID 1.

- Transport: Modbus RTU over RS485
- Linux serial device during test: `/dev/ttyUSB0`
- Serial: 38400 baud, 8 data bits, no parity, 1 stop bit
- Slave ID: 1
- Read function: FC03
- Address offset: 0
- Validated live range: `0x1100` through `0x1121`
- Validated operating-state register: `0x1200`
- Stability: 10 of 10 reads successful for 34 registers at `0x1100`
- Writes remain disabled.

The former `0x0001-0x00E6` catalog was replaced by the working Windows-HMI map. The merged catalog contains 269 workbook registers plus 19 HMI-only registers, for 288 points total. PCS2-PCS4 IDs are not yet confirmed and remain disabled in the commissioning template.
