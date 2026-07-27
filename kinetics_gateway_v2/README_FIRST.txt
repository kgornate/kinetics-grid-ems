KINETICS GATEWAY V2.2 - FOUR PCS MODBUS RTU/RS485 UPDATE
Date: 2026-07-26

This package was created from the FRDM i.MX93 backup:
kinetics_gateway_backup_20260726_141428(1).zip

CONFIRMED DESIGN
- BMS remains on the existing Modbus TCP implementation.
- Four PCS units will use one shared Modbus RTU/RS485 bus.
- Each PCS is represented as pcs_1, pcs_2, pcs_3 and pcs_4.
- The four slave IDs are currently staged as 1,2,3,4 but are UNCONFIRMED.

SAFETY
- The existing active etc/config.json is unchanged.
- Existing systemd and network files are unchanged.
- The new RTU template has pcs.enabled=false and write_enabled=false.
- Do not enable RTU polling until serial settings and slave IDs are confirmed.
- Do not enable writes until data types, scaling and command definitions are confirmed.

UPDATE EXISTING BOARD WITHOUT REPLACING CONFIG OR SYSTEMD
1. Copy this package to the board and extract it.
2. Run as root:
   sh opt/kinetics-gateway/backend/deployment/update_pcs_rtu_on_imx93.sh
3. The script updates only PCS/multi-PCS application files and installs pyserial.
4. It does not replace /etc/kinetics-gateway, network scripts or systemd units.

STAGING CONFIG
opt/kinetics-gateway/backend/configs/kinetics_hardware_bms_4pcs_rtu_template.json

READ-ONLY PCS TEST TOOL
opt/kinetics-gateway/backend/tools/pcs_rtu_probe.py

FULL NOTES
opt/kinetics-gateway/backend/PCS_RTU_INTEGRATION.md

VALIDATION
- 21 automated tests passed.
- Legacy one-PCS TCP config remains backward compatible.
- Four-PCS mock RTU snapshot and shared-bus model were tested.
- Modbus RTU CRC and FC03 frame parsing were tested.
