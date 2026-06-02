# EMS Web API Curl Test Sheet

Replace `<IMX93_IP>` with:

- Ethernet IP: `192.168.10.2`  (ignore this for now)
- Wi-Fi IP: 10.55.41.131

IMX93_IP = 10.55.41.131
## 1. Health

```bash
curl http://<IMX93_IP>:8000/api/gateway/health
```

## 2. Gateway Status

```bash
curl http://<IMX93_IP>:8000/api/gateway/status
```

## 3. Network Status

```bash
curl http://<IMX93_IP>:8000/api/gateway/network
```

## 4. Asset List

```bash
curl http://<IMX93_IP>:8000/api/assets
```

## 5. Combined Latest Telemetry

```bash
curl http://<IMX93_IP>:8000/api/telemetry/latest
```

## 6. Asset Latest Telemetry

```bash
curl http://<IMX93_IP>:8000/api/assets/bms_1/telemetry/latest
curl http://<IMX93_IP>:8000/api/assets/pcs_1/telemetry/latest
curl http://<IMX93_IP>:8000/api/assets/chiller_1/telemetry/latest
```

## 7. Telemetry Keys

```bash
curl http://<IMX93_IP>:8000/api/assets/bms_1/telemetry/keys
curl http://<IMX93_IP>:8000/api/assets/pcs_1/telemetry/keys
curl http://<IMX93_IP>:8000/api/assets/chiller_1/telemetry/keys
```

## 8. Timeseries from Local Logs

```bash
curl "http://<IMX93_IP>:8000/api/assets/bms_1/telemetry/timeseries?keys=stack_voltage_v,stack_soc_percent&date=2026-06-01&limit=100"
```

Use actual field names from your CSV files or from telemetry keys API.

## 9. Chiller Command

```bash
curl -X POST http://<IMX93_IP>:8000/api/assets/chiller_1/commands \
  -H "Content-Type: application/json" \
  -d '{"command":"SET_TEMP","value":25.0}'
```

```bash
curl -X POST http://<IMX93_IP>:8000/api/assets/chiller_1/commands \
  -H "Content-Type: application/json" \
  -d '{"command":"CHILLER_ON"}'
```

## 10. PCS Command

```bash
curl -X POST http://<IMX93_IP>:8000/api/assets/pcs_1/commands \
  -H "Content-Type: application/json" \
  -d '{"command":"PCS_SET_ACTIVE_POWER","value":20.0}'
```

## 11. BMS Command

```bash
curl -X POST http://<IMX93_IP>:8000/api/assets/bms_1/commands \
  -H "Content-Type: application/json" \
  -d '{"command":"START_BMS_PRECHARGE"}'
```

## 12. SSE Live Stream

```bash
curl http://<IMX93_IP>:8000/api/stream/telemetry
```

Expected: telemetry events should continuously print until Ctrl+C.

## 13. Existing Log APIs on Port 7000

```bash
curl http://<IMX93_IP>:7000/api/health
curl http://<IMX93_IP>:7000/api/logs/assets
curl "http://<IMX93_IP>:7000/api/logs/files?asset_id=bms_1"
curl "http://<IMX93_IP>:7000/api/logs/telemetry?asset_id=bms_1&date=2026-06-01&limit=20"
```

## 14. Static Compile Check on i.MX93

```bash
cd /root/kinetics-grid-ems/imx93_gateway
python3 -m py_compile config.py main.py network/ems_web_api_server.py
```

## 15. Example Gateway Run Commands

All assets:

```bash
python3 main.py --pc-ip 192.168.10.1
```

BMS only:

```bash
python3 main.py --no-chiller --no-pcs --bms-host 192.168.10.1 --pc-ip 192.168.10.1
```

PCS only:

```bash
python3 main.py --no-chiller --no-bms --pcs-host 192.168.10.1 --pc-ip 192.168.10.1
```

Chiller only:

```bash
python3 main.py --no-bms --no-pcs --pc-ip 192.168.10.1
```

Disable web API if needed:

```bash
python3 main.py --no-web-api --pc-ip 192.168.10.1
```

Override web API port:

```bash
python3 main.py --web-api-port 8080 --pc-ip 192.168.10.1
```
