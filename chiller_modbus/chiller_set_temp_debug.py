from pymodbus.client import ModbusSerialClient
import sys
import time

PORT = "/dev/ttyUSB0"
SLAVE_ID = 1

if len(sys.argv) != 2:
    print("Usage: python3 chiller_set_temp_debug.py 25.0")
    exit(1)

temp_c = float(sys.argv[1])
raw_value = int(temp_c * 10)

client = ModbusSerialClient(
    port=PORT,
    baudrate=9600,
    bytesize=8,
    parity="N",
    stopbits=1,
    timeout=2,
    retries=1
)

client.connect()

def read_temp_setpoint():
    result = client.read_holding_registers(
        address=205,
        count=1,
        device_id=SLAVE_ID
    )

    if result.isError():
        print("Read register 205 failed:", result)
        return None

    raw = result.registers[0]
    print("Register 205 raw:", raw)
    print("Register 205 temp:", raw / 10.0, "degC")
    return raw

print("Before write:")
before = read_temp_setpoint()

time.sleep(0.5)

print("\nWriting temperature...")
print("Requested temp:", temp_c, "degC")
print("Raw value:", raw_value)

write_result = client.write_register(
    address=205,
    value=raw_value,
    device_id=SLAVE_ID
)

print("Write result:", write_result)

time.sleep(1)

print("\nAfter write:")
after = read_temp_setpoint()

client.close()
