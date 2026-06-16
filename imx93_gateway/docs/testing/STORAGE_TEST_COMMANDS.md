# Storage Test Commands

## Static checks

```bash
python3 -m py_compile $(find . -path './__pycache__' -prune -o -name '*.py' -print)
```

## Unit/compatibility checks

```bash
python3 test_legacy_compatibility.py
python3 test_asset_adapters.py
python3 test_command_dispatcher.py
python3 test_telemetry_pipeline.py
python3 test_runtime_config.py
python3 test_asset_protocol_config.py
python3 test_operator_telemetry_view.py
python3 test_storage_abstraction.py
```

## Run gateway

```bash
python3 -u main.py \
  --config-file configs/actual_network_assets.json \
  --no-chiller \
  2>&1 | tee gateway_run.log
```

## Test log API

Replace IP with your board IP if needed.

```bash
curl -s http://127.0.0.1:7000/api/health
curl -s 'http://127.0.0.1:7000/api/storage/status?asset_id=pcs_1'
curl -s 'http://127.0.0.1:7000/api/storage/health?asset_id=pcs_1'
curl -s 'http://127.0.0.1:7000/api/storage/health?asset_id=bms_1'
curl -s 'http://127.0.0.1:7000/api/logs/assets'
```

From Windows PowerShell:

```powershell
$IMX_ETH_IP = "192.168.10.2"
Invoke-RestMethod -Uri "http://$IMX_ETH_IP:7000/api/storage/health?asset_id=pcs_1" | ConvertTo-Json -Depth 20
Invoke-RestMethod -Uri "http://$IMX_ETH_IP:7000/api/storage/health?asset_id=bms_1" | ConvertTo-Json -Depth 20
```

Expected result:

```text
status = healthy or degraded
base_path = /home/root/ems_logs_test
disk_free_bytes is present
telemetry_dir_exists is present
```
