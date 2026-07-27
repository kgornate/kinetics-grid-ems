# BMS-only quick start

Use `backend/configs/kinetics_hardware_bms_only.json` for the first BAU test.

- BMS polling: enabled
- PCS polling: disabled
- Gateway mode: read-only
- BMS writes: disabled
- PCS writes: disabled
- Fast/normal/slow/bulk schedules: enabled

After installation:

```bash
cp /opt/kinetics-gateway/backend/configs/kinetics_hardware_bms_only.json /etc/kinetics-gateway/config.json
systemctl restart kinetics-network.service kinetics-gateway.service
```
