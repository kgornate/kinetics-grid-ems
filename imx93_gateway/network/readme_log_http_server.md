1) To be used with network/log_http_server.py

Run Below commands to copy the respective files to i.mx93:

scp "C:\Users\KunalGupta\EMS_Ornte_Code_base\kinetics-grid-ems\imx93_gateway\config.py" root@192.168.10.2:~/kinetics-grid-ems/imx93_gateway/config.py

scp "C:\Users\KunalGupta\EMS_Ornte_Code_base\kinetics-grid-ems\imx93_gateway\main.py" root@192.168.10.2:~/kinetics-grid-ems/imx93_gateway/main.py

scp "C:\Users\KunalGupta\EMS_Ornte_Code_base\kinetics-grid-ems\imx93_gateway\services\log_query_service.py" root@192.168.10.2:~/kinetics-grid-ems/imx93_gateway/services/log_query_service.py

scp "C:\Users\KunalGupta\EMS_Ornte_Code_base\kinetics-grid-ems\imx93_gateway\network\log_http_server.py" root@192.168.10.2:~/kinetics-grid-ems/imx93_gateway/network/log_http_server.py



To test on I.MX93 for http_log_query_over_etehrnet:

2) Test on i.MX93

Run:

--> cd ~/kinetics-grid-ems/imx93_gateway
--> python3 -m py_compile config.py main.py services/log_query_service.py network/log_http_server.py

No output means syntax OK.

3) Then run:

--> python3 main.py --pc-ip 192.168.10.1

4) Expected startup print:

[MAIN] Starting HTTP log API server...
[LOG_HTTP] Log HTTP server started | http://0.0.0.0:7000

5) Test from PC browser

Open these in browser:

--> http://192.168.10.2:7000/api/health
--> http://192.168.10.2:7000/api/storage/status
--> http://192.168.10.2:7000/api/logs/files
--> http://192.168.10.2:7000/api/logs/telemetry?date=2026-05-26&limit=20
--> http://192.168.10.2:7000/api/logs/events?limit=20
--> http://192.168.10.2:7000/api/logs/errors?limit=20