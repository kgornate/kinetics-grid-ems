Testing commands for updated CLI

First, place files like this on i.MX93 later:

cd /root/kinetics-grid-ems/imx93_gateway

mkdir -p drivers

# Put register map here:
drivers/bms_register_map.py

# Put CLI here:
bms_modbus_tcp_cli.py

Create empty init file if not already present:

touch drivers/__init__.py
1. Syntax/import test

Run this before connecting to ModSim:

python3 -m py_compile drivers/bms_register_map.py
python3 -m py_compile bms_modbus_tcp_cli.py

Then:

python3 bms_modbus_tcp_cli.py --help
2. Read core telemetry from ModSim

If ModSim is running on PC at 192.168.10.1:502:

python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --read-core

If you use port 1502:

python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 1502 --unit-id 1 --read-core
3. Read alarms/status
python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --read-alarms
4. Read everything
python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --read-all
5. Write control commands
python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --start-precharge
python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --stop-precharge
python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --start-insulation
python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --fan-on
python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --fan-off
python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --fan-auto
python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --reset-bcu
6. If ModSim addressing is shifted

Try:

python3 bms_modbus_tcp_cli.py --host 192.168.10.1 --port 502 --unit-id 1 --address-offset 1 --r