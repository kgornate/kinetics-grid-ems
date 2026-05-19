from pymodbus.client import ModbusSerialClient
import time

PORT = "/dev/ttyUSB0"
SLAVE_ID = 1

READ_MODE_MAP = {
    1: "Water pump circulation mode",
    2: "Refrigeration / Cooling mode",
    3: "Heating mode",
    4: "System automatic control mode"
}

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

print("Reading current chiller control mode...")
print("Register: 200")

time.sleep(0.2)

try:
    result = client.read_holding_registers(
        address=200,
        count=1,
        device_id=SLAVE_ID
    )

    if result.isError():
        print("Read mode error:", result)
    else:
        mode_value = result.registers[0]
        mode_name = READ_MODE_MAP.get(mode_value, "Unknown mode")

        print("Raw mode value:", mode_value)
        print("Current control mode:", mode_name)

except Exception as e:
    print("Read failed:", e)

client.close()
