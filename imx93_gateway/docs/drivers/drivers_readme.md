# Chiller Modbus Driver - i.MX93 EMS Gateway

## 1. Purpose of This File

`chiller_modbus_driver.py` is the Modbus RTU driver layer for the liquid cooling system / chiller.

This file is responsible for:

- Communicating with the chiller over RS485 Modbus RTU
- Reading chiller telemetry/status parameters
- Writing chiller control commands
- Reading back setting/control parameters
- Converting raw Modbus registers into clean software values
- Providing reusable APIs for the EMS Gateway backend

This driver is used by the i.MX93 Gateway application.

```text
Chiller
   ⇅ Modbus RTU / RS485
USB-RS485 Adapter
   ⇅ /dev/ttyUSB0
i.MX93 Gateway Backend
2. Source of Register Mapping

The driver is based on:

Liquid Cooling System Control Communication Protocol datasheet
Existing working scripts:
chiller_read.py
chiller_control.py
chiller_read_mode.py
chiller_set_mode.py
chiller_set_temp_debug.py
scan_chiller_id.py

The final driver combines the already-tested script logic into one reusable Python class:

ChillerModbusDriver
3. Serial Communication Configuration

The chiller communicates over RS485 using Modbus RTU.

Parameter	Value
Baudrate	9600
Data Bits	8
Parity	None
Stop Bits	1
Protocol	Modbus RTU
Physical Layer	RS485
Default Linux Port	/dev/ttyUSB0
Default Slave ID	1
Minimum Command Gap	>= 200 ms
4. Register Map Used
4.1 Telemetry / Status Registers

These are read using Modbus function code 0x04.

In pymodbus, this is:

read_input_registers()
Register	Parameter	Scaling
0	Water pump status	1 = RUNNING, 0 = STOPPED
1	Compressor 1 status	1 = RUNNING, 0 = STOPPED
2	Compressor 2 status	1 = RUNNING, 0 = STOPPED
3	Electric heater status	1 = RUNNING, 0 = STOPPED
4	Condensate fan status	1 = RUNNING, 0 = STOPPED
5	Outlet water temperature	value / 10
6	Return water temperature	value / 10
7	Outlet water pressure	value / 100
8	Return water pressure	value / 100
9	External ambient temperature	value / 10
10	Make-up water pump status	1 = ON, 0 = OFF
11	Fault alarm code	Raw fault code

Example:

Raw register value 384  → 38.4 °C
Raw register value 27   → 0.27 Bar
4.2 Control / Setting Registers

These are holding registers.

They are read using function code 0x03:

read_holding_registers()

They are written using function code 0x06:

write_register()
Register	Parameter	Access
200	Control mode	Read/Write
201	System ON/OFF enable	Read/Write
205	Unit set temperature	Read/Write
5. Control Mode Mapping

The chiller has different values for writing mode and reading mode.

5.1 Write Values

When setting the control mode:

Write Value	Mode
0	System automatic control mode
1	Refrigeration / Cooling mode
2	Heating mode
3	Water pump circulation mode

Example:

python3 imx93_gateway/drivers/chiller_modbus_driver.py set_mode 1

This sets the chiller to refrigeration/cooling mode.

5.2 Readback Values

When reading back the control mode:

Readback Value	Mode
1	Water pump circulation mode
2	Refrigeration / Cooling mode
3	Heating mode
4	System automatic control mode

This is why the driver has separate maps:

WRITE_MODE_MAP
READ_MODE_MAP
WRITE_VALUE_TO_EXPECTED_READBACK

Example:

Write 1 → Refrigeration / Cooling mode
Readback expected → 2
6. Main Class

The main class is:

ChillerModbusDriver

Example usage inside another Python file:

from imx93_gateway.drivers.chiller_modbus_driver import ChillerModbusDriver

driver = ChillerModbusDriver(
    port="/dev/ttyUSB0",
    slave_id=1
)

if driver.connect():
    state = driver.read_all_parameters()
    print(state)

    driver.close()
7. Available Driver APIs
7.1 Connection APIs
connect()
close()
is_connected()
7.2 Telemetry Read APIs
read_all_parameters()
read_all_parameters_dict()
read_fault_alarm_code()
read_all_input_registers_0_to_90()

Main API:

state = driver.read_all_parameters()

This reads input registers 0 to 11.

7.3 Setting Read APIs
read_control_mode()
read_on_off_enable()
read_set_temperature()
read_setting_parameters()

Main setting read API:

settings = driver.read_setting_parameters()

This reads holding registers 200 to 208.

7.4 Control / Write APIs
turn_on()
turn_off()
set_control_mode(mode)
set_temperature(temperature_celsius)
apply_basic_control()

Examples:

driver.turn_on()
driver.turn_off()
driver.set_temperature(25.0)
driver.set_control_mode(1)
driver.set_control_mode("cooling")
7.5 Slave ID Scan API
scan_slave_ids()

Example:

found_ids = driver.scan_slave_ids(start_id=1, end_id=128)
8. How To Test This Driver on i.MX93

First go to the repo root on i.MX93:

cd ~/kinetics-grid-ems

Make sure the USB-RS485 adapter is connected and visible:

ls /dev/ttyUSB*

Expected:

/dev/ttyUSB0

If the device is different, pass it using --port.

Example:

python3 imx93_gateway/drivers/chiller_modbus_driver.py read --port /dev/ttyUSB1
9. Test Commands
9.1 Read Chiller Telemetry
python3 imx93_gateway/drivers/chiller_modbus_driver.py read

Expected output:

[MODBUS] Connected on /dev/ttyUSB0
[MODBUS] Raw telemetry registers 0-11: [1, 0, 0, 0, 0, 384, 381, 27, 7, 374, 1, 0]

---------------- CHILLER TELEMETRY ----------------
water_pump                   : RUNNING
compressor1                  : STOPPED
compressor2                  : STOPPED
electric_heater              : STOPPED
condensate_fan               : STOPPED
outlet_water_temp             : 38.4
return_water_temp             : 38.1
outlet_water_pressure         : 0.27
return_water_pressure         : 0.07
ambient_temp                  : 37.4
makeup_pump                   : ON
fault_code                    : 0
communication_status          : online
9.2 Read Setting Registers
python3 imx93_gateway/drivers/chiller_modbus_driver.py settings

This reads holding registers 200 to 208.

9.3 Read Current Mode
python3 imx93_gateway/drivers/chiller_modbus_driver.py read_mode
9.4 Read ON/OFF Status
python3 imx93_gateway/drivers/chiller_modbus_driver.py read_onoff
9.5 Read Set Temperature
python3 imx93_gateway/drivers/chiller_modbus_driver.py read_temp
9.6 Set Temperature

Use carefully.

python3 imx93_gateway/drivers/chiller_modbus_driver.py set_temp 25.0

This writes:

Register 205 = 250

Because temperature scaling is:

25.0 °C × 10 = 250

By default, the driver verifies the write by reading back register 205.

To disable verification:

python3 imx93_gateway/drivers/chiller_modbus_driver.py set_temp 25.0 --no-verify
9.7 Set Control Mode

Use carefully.

Cooling mode:

python3 imx93_gateway/drivers/chiller_modbus_driver.py set_mode 1

Heating mode:

python3 imx93_gateway/drivers/chiller_modbus_driver.py set_mode 2

Water pump circulation mode:

python3 imx93_gateway/drivers/chiller_modbus_driver.py set_mode 3

Automatic mode:

python3 imx93_gateway/drivers/chiller_modbus_driver.py set_mode 0

You can also use names:

python3 imx93_gateway/drivers/chiller_modbus_driver.py set_mode cooling
python3 imx93_gateway/drivers/chiller_modbus_driver.py set_mode heating
python3 imx93_gateway/drivers/chiller_modbus_driver.py set_mode pump
python3 imx93_gateway/drivers/chiller_modbus_driver.py set_mode auto
9.8 Turn Chiller ON

Use carefully.

python3 imx93_gateway/drivers/chiller_modbus_driver.py on

This writes:

Register 201 = 1
9.9 Turn Chiller OFF

Use carefully.

python3 imx93_gateway/drivers/chiller_modbus_driver.py off

This writes:

Register 201 = 0
9.10 Scan Chiller Slave ID
python3 imx93_gateway/drivers/chiller_modbus_driver.py scan

This scans slave IDs from 1 to 128.

10. Recommended Safe Test Order

Follow this order during testing.

Step 1: Check serial port
ls /dev/ttyUSB*
Step 2: Read telemetry only
python3 imx93_gateway/drivers/chiller_modbus_driver.py read

Do this first. This is safe because it only reads data.

Step 3: Read settings
python3 imx93_gateway/drivers/chiller_modbus_driver.py settings

This is also safe because it only reads data.

Step 4: Read current mode and set temperature
python3 imx93_gateway/drivers/chiller_modbus_driver.py read_mode
python3 imx93_gateway/drivers/chiller_modbus_driver.py read_temp
Step 5: Test set temperature

Only do this if the chiller is allowed to accept setpoint changes.

python3 imx93_gateway/drivers/chiller_modbus_driver.py set_temp 25.0
Step 6: Test mode change

Only do this if the chiller can safely change mode.

python3 imx93_gateway/drivers/chiller_modbus_driver.py set_mode 1
Step 7: Test ON/OFF

Only do this when the actual system is safe to start/stop.

python3 imx93_gateway/drivers/chiller_modbus_driver.py on
python3 imx93_gateway/drivers/chiller_modbus_driver.py off
11. Expected File Location

This file should be located at:

kinetics-grid-ems/
└── imx93_gateway/
    └── drivers/
        ├── __init__.py
        ├── chiller_modbus_driver.py
        └── README.md
12. Why This Driver Has Lock and Delay

The driver uses:

threading.Lock()

and enforces:

minimum 200 ms gap between Modbus instructions

Reason:

Later, the EMS gateway will run multiple threads:

Thread 1: Polling chiller telemetry
Thread 2: Receiving TCP command from PC
Thread 3: Sending UDP telemetry to PC

Both polling and control commands use the same RS485 bus:

/dev/ttyUSB0

So the lock prevents simultaneous Modbus read/write access.

Without lock:

Polling thread reads input registers
TCP command thread writes set temperature
Both access serial port at same time
Result: timeout / corrupted Modbus transaction

With lock:

Only one Modbus transaction happens at a time
13. What This Driver Replaces

This final driver replaces the separate test scripts:

chiller_read.py
chiller_control.py
chiller_read_mode.py
chiller_set_mode.py
chiller_set_temp_debug.py
scan_chiller_id.py

Those scripts are still useful as reference, but the EMS gateway should now use:

ChillerModbusDriver
14. Next Development Step

After this driver is tested, the next file to implement is:

imx93_gateway/services/chiller_gateway_service.py

That service will act as the bridge between:

Modbus driver
TCP command server
UDP telemetry streamer
Latest chiller state

The service will do:

1. Periodically call driver.read_all_parameters()
2. Store latest chiller state
3. Provide latest state to UDP telemetry streamer
4. Receive command from TCP server
5. Call driver.turn_on(), turn_off(), set_temperature(), set_control_mode()
6. Return ACK/NACK response to TCP client
15. Final Gateway Flow

After completing the service, TCP server, UDP streamer, and main file, the final flow will be:

Chiller
   ⇅ Modbus RTU / RS485
ChillerModbusDriver
   ⇅
ChillerGatewayService
   ⇅
TCP Command Server + UDP Telemetry Streamer
   ⇅ Ethernet
PC Dashboard Test / Flutter GUI
16. Git Commit Suggestion

After testing this driver successfully:

git status
git add imx93_gateway/drivers/chiller_modbus_driver.py
git add imx93_gateway/drivers/README.md
git commit -m "Add chiller Modbus RTU driver and usage README"
git push
17. Troubleshooting
Problem: No /dev/ttyUSB0

Check connected USB serial devices:

ls /dev/ttyUSB*
ls /dev/ttyACM*

Then run with correct port:

python3 imx93_gateway/drivers/chiller_modbus_driver.py read --port /dev/ttyUSB1
Problem: Permission denied

Run as root or adjust permissions.

sudo python3 imx93_gateway/drivers/chiller_modbus_driver.py read

On your i.MX93 board, you are usually already running as root.

Problem: No response from chiller

Check:

1. RS485 A/B wiring
2. USB-RS485 adapter connection
3. Correct slave ID
4. Correct baudrate: 9600
5. Correct serial port: /dev/ttyUSB0
6. Chiller powered ON
7. RS485 ground/reference connection if required

Try scanning:

python3 imx93_gateway/drivers/chiller_modbus_driver.py scan
Problem: Read works but write does not work

Check:

1. Whether chiller allows BMS/external control mode
2. Whether register 200 must be set to correct mode first
3. Whether chiller has any lock/protection condition
4. Whether ON/OFF enable is allowed from RS485
5. Whether system is in alarm/fault state

Read current setting registers:

python3 imx93_gateway/drivers/chiller_modbus_driver.py settings
Problem: Mode verification looks confusing

Mode write values and mode readback values are different.

Example:

Write 1 = Refrigeration / Cooling mode
Readback 2 = Refrigeration / Cooling mode

This is expected as per the protocol. The driver already handles this mapping internally.