Kinetics Gateway V2.3 - PCS HMI-map Modbus RTU update

Confirmed on hardware:
- PCS1 Modbus RTU over one USB-RS485 adapter
- /dev/ttyUSB0 during commissioning
- 38400 baud, 8N1
- Unit ID 1
- FC03
- Direct register addressing (offset 0)
- 0x1100 count 34: 10/10 successful reads
- 0x1200 operating-state read successful

The actual PCS catalog now comes from the working Windows HMI package:
- 269 PCS.xlsx registers
- 19 additional HMI-config registers
- 288 catalog points total

Safety:
- PCS writes are disabled.
- PCS2-PCS4 are disabled until their actual slave IDs are confirmed.
- Existing BMS code/catalog, /etc config, networking, Cloudflare and systemd units are not replaced by the patch updater.
