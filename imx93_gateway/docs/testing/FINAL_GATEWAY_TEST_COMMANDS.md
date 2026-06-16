# Final EMS Gateway Test Commands

Run these commands after deploying the gateway package on i.MX93.

## 1. Static code checks

```bash
cd /root/kinetics-grid-ems/imx93_gateway
python3 -m py_compile $(find . -path './__pycache__' -prune -o -name '*.py' -print)
```

## 2. Unit and compatibility tests

```bash
python3 test_legacy_compatibility.py
python3 test_asset_adapters.py
python3 test_command_dispatcher.py
python3 test_telemetry_pipeline.py
python3 test_runtime_config.py
python3 test_asset_protocol_config.py
python3 test_operator_telemetry_view.py
python3 test_storage_abstraction.py
python3 test_health_monitoring.py
python3 test_dynamic_asset_runtime.py
python3 test_log_filter_abstraction.py
```

## 3. Print runtime config

```bash
python3 main.py --config-file configs/actual_network_assets.json --print-runtime-config
```

Confirm:

```text
PCS_HOST = 192.168.1.200
BMS_MODBUS_HOST = 192.168.10.1
PC_TELEMETRY_IP = 192.168.10.1
WEB_API_PORT = 8000
LOG_HTTP_PORT = 7000
```

## 4. Start gateway

With chiller enabled:

```bash
python3 -u main.py --config-file configs/actual_network_assets.json 2>&1 | tee gateway_run.log
```

Without chiller:

```bash
python3 -u main.py --config-file configs/actual_network_assets.json --no-chiller 2>&1 | tee gateway_run.log
```

## 5. Check listening ports

```bash
ss -ltnp | grep -E ':6000|:7000|:8000'
```

Expected:

```text
0.0.0.0:6000
0.0.0.0:7000
0.0.0.0:8000
```

## 6. Web API checks

Use the active Wi-Fi IP from:

```bash
ip -br addr show mlan0
```

Example:

```bash
curl -s http://127.0.0.1:8000/api/gateway/health | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/assets | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/telemetry/latest | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/telemetry/operator | python3 -m json.tool
```

## 7. Health API checks

```bash
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/health/assets | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/diagnostics | python3 -m json.tool
```

## 8. Log API checks

```bash
curl -s http://127.0.0.1:7000/api/logs/assets | python3 -m json.tool
curl -s 'http://127.0.0.1:7000/api/storage/health?asset_id=pcs_1' | python3 -m json.tool
curl -s 'http://127.0.0.1:7000/api/storage/health?asset_id=bms_1' | python3 -m json.tool
```

## 9. Log filter checks

```bash
DATE=$(date +%F)

curl -s "http://127.0.0.1:7000/api/logs/telemetry?asset_id=pcs_1&date=$DATE&limit=20" | python3 -m json.tool

curl -s "http://127.0.0.1:7000/api/logs/telemetry?asset_id=pcs_1&date=$DATE&fields=timestamp,active_power_kw,dc_voltage_v&limit=20" | python3 -m json.tool

curl -s "http://127.0.0.1:7000/api/logs/telemetry?asset_id=pcs_1&date=$DATE&start_time=10:00&end_time=12:00&limit=50" | python3 -m json.tool

curl -s "http://127.0.0.1:7000/api/logs/events?asset_id=pcs_1&status=success&limit=50" | python3 -m json.tool

curl -s "http://127.0.0.1:7000/api/logs/errors?asset_id=bms_1&source=modbus&limit=50" | python3 -m json.tool
```

## 10. Windows PowerShell checks

```powershell
$IMX_ETH_IP = "192.168.10.2"
$IMX_WIFI_IP = "192.168.88.16"

Test-NetConnection $IMX_ETH_IP -Port 6000
Test-NetConnection $IMX_ETH_IP -Port 7000
Test-NetConnection $IMX_WIFI_IP -Port 8000

Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/telemetry/operator" | ConvertTo-Json -Depth 40
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/health" | ConvertTo-Json -Depth 40
Invoke-RestMethod -Uri "http://$IMX_ETH_IP:7000/api/logs/assets" | ConvertTo-Json -Depth 30
```
