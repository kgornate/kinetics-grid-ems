# Dynamic Asset Runtime Test Commands

## Start gateway

```bash
python3 -u main.py \
  --config-file configs/actual_network_assets.json \
  --no-chiller \
  2>&1 | tee gateway_run.log
```

## Test asset catalog locally on i.MX93

```bash
curl -s http://127.0.0.1:8000/api/assets | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/assets/pcs_1 | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/assets/bms_1 | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/assets/chiller_1 | python3 -m json.tool
```

## Test health catalog locally

```bash
curl -s http://127.0.0.1:8000/api/health/assets | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/health/assets/pcs_1 | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/diagnostics | python3 -m json.tool
```

## Test from Windows browser or PowerShell

Use the current board Wi-Fi IP. Example:

```text
http://192.168.88.16:8000/api/assets
http://192.168.88.16:8000/api/health/assets
http://192.168.88.16:8000/api/diagnostics
```

PowerShell:

```powershell
$IMX_WIFI_IP = "192.168.88.16"

Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/assets" | ConvertTo-Json -Depth 40
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/health/assets" | ConvertTo-Json -Depth 40
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/diagnostics" | ConvertTo-Json -Depth 40
```

## Expected result

`/api/assets` should return an `assets` list with fields like:

```text
asset_id
asset_key
asset_type
enabled
running
online
protocol
profile
vendor
runtime_mode
telemetry_available
```

For the current actual network, expected runtime modes are typically:

```text
pcs_1      -> active_service if PCS service started successfully
bms_1      -> active_service if BMS service started successfully
chiller_1  -> disabled when --no-chiller is used
```

If an extra future asset is added to config but no service exists yet, it should appear as `configured_only`, `configured_future`, or `disabled` depending on the config.
