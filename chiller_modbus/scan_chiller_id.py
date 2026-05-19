from pymodbus.client import ModbusSerialClient
import time

PORT = "/dev/ttyUSB0"

client = ModbusSerialClient(
    port=PORT,
    baudrate=9600,
    bytesize=8,
    parity="N",
    stopbits=1,
    timeout=1,
    retries=1
)

if not client.connect():
    print("Could not open", PORT)
    exit(1)

print("Scanning chiller slave IDs 1 to 128...")

found = False

for slave_id in range(1, 129):
    time.sleep(0.2)

    try:
        result = client.read_input_registers(
            address=0,
            count=1,
            device_id=slave_id
        )

        if not result.isError():
            print("Found chiller slave ID:", slave_id)
            print("Register 0 value:", result.registers[0])
            found = True
            break

    except Exception:
        pass

if not found:
    print("No chiller found from slave ID 1 to 128")

client.close()
