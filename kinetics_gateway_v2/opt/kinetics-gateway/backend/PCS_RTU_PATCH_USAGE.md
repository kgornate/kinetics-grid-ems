# PCS HMI-map patch usage

1. Run `sh deployment/update_pcs_hmi_map_on_imx93.sh`.
2. Confirm the gateway and BMS remain healthy. The updater does not replace `/etc/kinetics-gateway/config.json`.
3. Confirm `/dev/ttyUSB0` exists and the Windows PCS software is disconnected.
4. Enable only PCS1 in read-only mode with `sh /opt/kinetics-gateway/backend/deployment/enable_pcs1_readonly_on_imx93.sh`.
5. Check `journalctl -u kinetics-gateway.service -f` and `GET /api/pcs/all`.
6. To immediately stop PCS polling without stopping the BMS gateway, run `sh /opt/kinetics-gateway/backend/deployment/disable_pcs_polling_on_imx93.sh`.

Writes remain disabled. PCS2-PCS4 remain disabled until their actual slave IDs are confirmed.
