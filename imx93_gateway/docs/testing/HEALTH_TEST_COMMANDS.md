# Health Monitoring Test Commands

## Run gateway

```bash
python3 -u main.py \
  --config-file configs/actual_network_assets.json \
  --no-chiller \
  2>&1 | tee gateway_run.log
```

## i.MX93 local tests

```bash
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/health/gateway | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/health/assets | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/health/assets/pcs_1 | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/health/assets/bms_1 | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/diagnostics | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/diagnostics/assets/bms_1 | python3 -m json.tool
```

## Windows PowerShell tests

```powershell
$IMX_WIFI_IP = "192.168.88.16"

Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/health" | ConvertTo-Json -Depth 40
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/health/gateway" | ConvertTo-Json -Depth 40
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/health/assets" | ConvertTo-Json -Depth 40
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/health/assets/pcs_1" | ConvertTo-Json -Depth 40
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/health/assets/bms_1" | ConvertTo-Json -Depth 40
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/diagnostics" | ConvertTo-Json -Depth 40
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/diagnostics/assets/bms_1" | ConvertTo-Json -Depth 40
```

## Expected behavior

```text
/api/gateway/health still returns simple Web API server health.
/api/health returns full gateway + asset health.
/api/health/assets returns chiller/PCS/BMS health map.
/api/diagnostics returns reason and recommended action per asset.
```
