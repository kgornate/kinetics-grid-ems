# EMS Gateway End-to-End Test Commands - Actual Network

## Network architecture

```text
eth0  -> Flutter / Windows PC / BMS simulator
        i.MX93 eth0 = 192.168.10.2/24
        Windows PC  = 192.168.10.1

eth1  -> Real NJOY PCS / inverter
        i.MX93 eth1 = 192.168.1.2/24
        PCS IP      = 192.168.1.200
        PCS port    = 502
        PCS unit    = 1

mlan0 -> Wi-Fi / web dashboard side
        i.MX93 mlan0 = 10.204.132.131/24
        Web API base = http://10.204.132.131:8000
```

## i.MX93 network checks

```bash
ip -br addr show eth0
ip -br addr show eth1
ip -br addr show mlan0
ip route
```

Expected:

```text
eth0  -> 192.168.10.2/24
eth1  -> 192.168.1.2/24
mlan0 -> 10.204.132.131/24
```

Check PC and PCS reachability:

```bash
ping -c 4 192.168.10.1
ping -c 4 192.168.1.200
nc -vz 192.168.1.200 502
```

If `nc` is not available:

```bash
python3 - <<'PY'
import socket
for host, port in [("192.168.1.200", 502)]:
    s = socket.socket()
    s.settimeout(3)
    try:
        s.connect((host, port))
        print(f"OK: connected to {host}:{port}")
    except Exception as e:
        print(f"ERROR: cannot connect to {host}:{port}: {e}")
    finally:
        s.close()
PY
```

## Prepare gateway folder

```bash
cd /root/kinetics-grid-ems/imx93_gateway
```

## Static checks

```bash
python3 -m py_compile $(find . -path './__pycache__' -prune -o -name '*.py' -print)
```

Run compatibility tests:

```bash
python3 test_legacy_compatibility.py
python3 test_asset_adapters.py
python3 test_command_dispatcher.py
python3 test_telemetry_pipeline.py
python3 test_runtime_config.py
python3 test_asset_protocol_config.py
```

## Print merged runtime config

```bash
python3 main.py \
  --config-file configs/actual_network_assets.json \
  --print-runtime-config
```

Confirm values:

```text
PC_TELEMETRY_IP = 192.168.10.1
PCS_HOST        = 192.168.1.200
PCS_PORT        = 502
PCS_UNIT_ID     = 1
BMS_MODBUS_HOST = 192.168.10.1
BMS_MODBUS_PORT = 502
BMS_UNIT_ID     = 1
WEB_API_PORT    = 8000
LOG_HTTP_PORT   = 7000
```

## Run gateway with actual network profile

```bash
python3 -u main.py \
  --config-file configs/actual_network_assets.json \
  2>&1 | tee gateway_run.log
```

If chiller is not connected:

```bash
python3 -u main.py \
  --config-file configs/actual_network_assets.json \
  --no-chiller \
  2>&1 | tee gateway_run.log
```

Legacy CLI style is still supported:

```bash
python3 -u main.py \
  --pc-ip 192.168.10.1 \
  --pcs-host 192.168.1.200 \
  --pcs-port 502 \
  --pcs-unit 1 \
  --bms-host 192.168.10.1 \
  --bms-port 502 \
  --bms-unit 1 \
  --web-api-port 8000 \
  --log-http-port 7000 \
  2>&1 | tee gateway_legacy_cli_run.log
```

## Check listening ports on i.MX93

```bash
ss -ltnp | grep -E ':6000|:7000|:8000'
```

Expected:

```text
0.0.0.0:6000  TCP command server
0.0.0.0:7000  HTTP log API
0.0.0.0:8000  Web dashboard REST/SSE API
```

## Windows PowerShell variables

```powershell
$IMX_ETH_IP  = "192.168.10.2"
$IMX_WIFI_IP = "10.204.132.131"
```

## Windows network tests

```powershell
Test-Connection $IMX_ETH_IP -Count 4
Test-NetConnection $IMX_ETH_IP -Port 6000
Test-NetConnection $IMX_ETH_IP -Port 7000
Test-NetConnection $IMX_WIFI_IP -Port 8000
```

## Web API tests over Wi-Fi

```powershell
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/gateway/health" | ConvertTo-Json -Depth 20
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/gateway/status" | ConvertTo-Json -Depth 40
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/assets" | ConvertTo-Json -Depth 40
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/telemetry/latest" | ConvertTo-Json -Depth 50
```

Asset telemetry:

```powershell
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/assets/pcs_1/telemetry/latest" | ConvertTo-Json -Depth 40
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/assets/bms_1/telemetry/latest" | ConvertTo-Json -Depth 40
Invoke-RestMethod -Uri "http://$IMX_WIFI_IP:8000/api/assets/chiller_1/telemetry/latest" | ConvertTo-Json -Depth 40
```

## Web API command tests

PCS read:

```powershell
$body = @{ command="PCS_READ"; request_id="WEB_PCS_READ_001" } | ConvertTo-Json -Compress
Invoke-RestMethod -Method Post -Uri "http://$IMX_WIFI_IP:8000/api/assets/pcs_1/commands" -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 40
```

BMS read:

```powershell
$body = @{ command="READ_BMS_ALL"; request_id="WEB_BMS_READ_001" } | ConvertTo-Json -Compress
Invoke-RestMethod -Method Post -Uri "http://$IMX_WIFI_IP:8000/api/assets/bms_1/commands" -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 40
```

Chiller read, only if chiller is enabled:

```powershell
$body = @{ command="READ_ALL"; request_id="WEB_CH_READ_001" } | ConvertTo-Json -Compress
Invoke-RestMethod -Method Post -Uri "http://$IMX_WIFI_IP:8000/api/assets/chiller_1/commands" -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 40
```

## Log API tests over eth0

```powershell
Invoke-RestMethod -Uri "http://$IMX_ETH_IP:7000/api/health" | ConvertTo-Json -Depth 20
Invoke-RestMethod -Uri "http://$IMX_ETH_IP:7000/api/logs/assets" | ConvertTo-Json -Depth 20
Invoke-RestMethod -Uri "http://$IMX_ETH_IP:7000/api/storage/status?asset_id=pcs_1" | ConvertTo-Json -Depth 20
Invoke-RestMethod -Uri "http://$IMX_ETH_IP:7000/api/storage/status?asset_id=bms_1" | ConvertTo-Json -Depth 20
```

Telemetry log query:

```powershell
$Date = Get-Date -Format "yyyy-MM-dd"
Invoke-RestMethod -Uri "http://$IMX_ETH_IP:7000/api/logs/telemetry?asset_id=pcs_1&date=$Date&limit=20" | ConvertTo-Json -Depth 40
Invoke-RestMethod -Uri "http://$IMX_ETH_IP:7000/api/logs/telemetry?asset_id=bms_1&date=$Date&limit=20" | ConvertTo-Json -Depth 40
```

## TCP command test over eth0

```powershell
$client = [System.Net.Sockets.TcpClient]::new($IMX_ETH_IP, 6000)
$stream = $client.GetStream()
$writer = [System.IO.StreamWriter]::new($stream)
$reader = [System.IO.StreamReader]::new($stream)
$writer.AutoFlush = $true

function Send-EmsTcpCommand($CommandObject) {
    $json = $CommandObject | ConvertTo-Json -Compress
    $writer.WriteLine($json)
    $line = $reader.ReadLine()
    $line | ConvertFrom-Json | ConvertTo-Json -Depth 40
}
```

Commands:

```powershell
Send-EmsTcpCommand @{ request_id="PS_STATUS_001"; command="STATUS" }
Send-EmsTcpCommand @{ request_id="PS_ALL_001"; command="READ_ALL_ASSETS" }
Send-EmsTcpCommand @{ request_id="PS_PCS_READ_001"; command="PCS_READ" }
Send-EmsTcpCommand @{ request_id="PS_BMS_READ_001"; command="READ_BMS_ALL" }
```

Close TCP session:

```powershell
$writer.Close()
$reader.Close()
$client.Close()
```

## UDP telemetry listener over eth0

Use this only when Flutter is closed, because both may need UDP port 5005.

```powershell
$udp = [System.Net.Sockets.UdpClient]::new(5005)
$remote = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Any, 0)
Write-Host "Listening for UDP telemetry on port 5005... Press Ctrl+C to stop."
while ($true) {
    $bytes = $udp.Receive([ref]$remote)
    $text = [System.Text.Encoding]::UTF8.GetString($bytes)
    Write-Host "From $($remote.Address):$($remote.Port)"
    $text | ConvertFrom-Json | ConvertTo-Json -Depth 50
}
```

Expected packet fields:

```text
type
gateway_id
asset_id
timestamp
status
data
pcs
bms
assets
```

## Pass criteria

```text
1. Static check passes.
2. All compatibility tests pass.
3. Gateway starts without fatal error.
4. Ports 6000, 7000, and 8000 listen on 0.0.0.0.
5. Flutter receives UDP telemetry.
6. Flutter TCP commands work.
7. Web dashboard API works at http://10.204.132.131:8000.
8. Log API and filters work.
9. Real PCS works over eth1 at 192.168.1.200:502.
10. BMS simulator works over eth0 at 192.168.10.1.
11. Existing dashboard behavior is unchanged.
```
