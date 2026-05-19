from pymodbus.client import ModbusSerialClient
import sys
import time

PORT = "/dev/ttyUSB0"
SLAVE_ID = 1   # change this if scanner finds another ID

if len(sys.argv) != 2:
    print("Usage:")
    print("  python3 chiller_control.py on")
    print("  python3 chiller_control.py off")
    exit(1)

cmd = sys.argv[1].lower()

if cmd == "on":
    value = 1
elif cmd == "off":
    value = 0
else:
    print("Invalid command. Use on or off.")
    exit(1)

client = ModbusSerialClient(
    port=PORT,
    baudrate=9600,
    bytesize=8,
    parity="N",
    stopbits=1,
    timeout=2,
    retries=1
)

if not client.connect():
    print("Failed to open", PORT)
    exit(1)

time.sleep(0.2)

try:
    result = client.write_register(
        address=201,
        value=value,
        device_id=SLAVE_ID
    )

    if result.isError():
        print("Modbus write error:", result)
    else:
        print("Chiller", cmd.upper(), "command sent successfully")

except Exception as e:
    print("Write failed:", e)

client.close()
