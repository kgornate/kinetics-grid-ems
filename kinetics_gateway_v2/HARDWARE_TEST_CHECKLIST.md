# Hardware Read-Only Commissioning Checklist

## 1. Physical wiring

```text
FRDM eth1 -> Ethernet switch
Switch -> BAU/BMS
Switch -> PCS
FRDM eth0 -> Engineering PC
FRDM mlan0 -> Wi-Fi/internet
```

## 2. Default gateway addresses

```text
eth1 primary:   10.30.4.2/24
eth1 secondary: 192.168.1.2/24
eth0:           192.168.10.2/24
```

Configure the PC Ethernet adapter as, for example:

```text
192.168.10.10/24
```

No default gateway is required on the PC-to-FRDM cable.

## 3. Verify network

```bash
ip -br address
ip route
ping -c 3 10.30.4.13
ping -c 3 192.168.1.200
```

Update the PCS IP in `/etc/kinetics-gateway/config.json` if it differs.

## 4. Check ports

```bash
nc -zv -w 2 10.30.4.13 503
nc -zv -w 2 10.30.4.13 504
nc -zv -w 2 10.30.4.13 505
nc -zv -w 2 10.30.4.13 506
nc -zv -w 2 10.30.4.13 507
nc -zv -w 2 192.168.1.200 502
```

## 5. Probe BAU/BCU Unit IDs

```bash
cd /opt/kinetics-gateway/backend
/opt/kinetics-gateway/venv/bin/python tools/modbus_probe.py \
  --host 10.30.4.13 \
  --source-ip 10.30.4.2 \
  --ports 503 504 505 506 507 \
  --unit-ids 1 2 3 4 5 127 \
  --address 0x0000 \
  --count 1 \
  --functions 3 4
```

This probe is read-only.

## 6. Start the gateway

```bash
systemctl restart kinetics-network.service
systemctl restart kinetics-gateway.service
systemctl status kinetics-network.service kinetics-gateway.service
journalctl -u kinetics-gateway.service -f
```

## 7. Login and inspect

```bash
curl -s http://127.0.0.1:8000/api/health
```

Use `/docs` from the PC:

```text
http://192.168.10.2:8000/docs
```

## 8. Run complete extraction report

```bash
cd /opt/kinetics-gateway/backend
KINETICS_CONFIG=/etc/kinetics-gateway/config.json \
/opt/kinetics-gateway/venv/bin/python tools/hardware_read_validation.py \
  --config /etc/kinetics-gateway/config.json \
  --output /mnt/ems-logs/kinetics-gateway/hardware_read_validation.json
```

## 9. Confirm point counts

Expected active cached points after successful extraction:

```text
BAU bank:             155
Each rack/BCU:        371
Power/environment:    131 total
PCS:                  230
```

A lower count can be valid if the final protocol/site configuration disables unsupported sections, but bad-quality values and block errors must be investigated.

## 10. Keep writes disabled

Verify:

```json
"mode": "read_only"
"bms": {"write_enabled": false}
"pcs": {"write_enabled": false}
```
