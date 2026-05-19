from pymodbus.client import ModbusSerialClient
import sys
import time

PORT = "/dev/ttyUSB0"
SLAVE_ID = 1

WRITE_MODE_MAP = {
    0: "System automatic control mode",
    1: "Refrigeration / Cooling mode",
    2: "Heating mode",
    3: "Water pump circulation mode"
}

READ_MODE_MAP = {
    1: "Water pump circulation mode",
    2: "Refrigeration / Cooling mode",
    3: "Heating mode",
    4: "System automatic control mode"
}

if len(sys.argv) != 2:
    print("Usage:")
    print("  python3 chiller_set_mode.py 0   # System automatic control mode")
    print("  python3 chiller_set_mode.py 1   # Refrigeration / Cooling mode")
    print("  python3 chiller_set_mode.py 2   # Heating mode")
    print("  python3 chiller_set_mode.py 3   # Water pump circulation mode")
    exit(1)

mode = int(sys.argv[1])

if mode not in WRITE_MODE_MAP:
    print("Invalid mode value.")
    print("Allowed values:")
    for k, v in WRITE_MODE_MAP.items():
        print(f"  {k} = {v}")
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

print("Writing control mode to chiller...")
print("Register: 200")
print("Write value:", mode)
print("Requested mode:", WRITE_MODE_MAP[mode])

time.sleep(0.2)

try:
    result = client.write_register(
        address=200,
        value=mode,
        device_id=SLAVE_ID
    )

    if result.isError():
        print("Mode write error:", result)
    else:
        print("Mode write command sent successfully")

    time.sleep(0.5)

    read_result = client.read_holding_registers(
        address=200,
        count=1,
        device_id=SLAVE_ID
    )

    if read_result.isError():
        print("Mode readback error:", read_result)
    else:
        read_value = read_result.registers[0]
        print("Readback value:", read_value)
        print("Current reported mode:", READ_MODE_MAP.get(read_value, "Unknown mode"))

except Exception as e:
    print("Operation failed:", e)

client.close()
