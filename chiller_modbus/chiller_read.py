from pymodbus.client import ModbusSerialClient
import time

PORT = "/dev/ttyUSB0"
SLAVE_ID = 1   # change this if scanner finds another ID

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
    result = client.read_input_registers(
        address=0,
        count=12,
        device_id=SLAVE_ID
    )

    if result.isError():
        print("Modbus read error:", result)
    else:
        regs = result.registers

        print("Raw registers:", regs)
        print("------------------------------")
        print("Water Pump:", "RUNNING" if regs[0] else "STOPPED")
        print("Compressor 1:", "RUNNING" if regs[1] else "STOPPED")
        print("Compressor 2:", "RUNNING" if regs[2] else "STOPPED")
        print("Electric Heater:", "RUNNING" if regs[3] else "STOPPED")
        print("Condensate Fan:", "RUNNING" if regs[4] else "STOPPED")
        print("Outlet Water Temp:", regs[5] / 10.0, "degC")
        print("Return Water Temp:", regs[6] / 10.0, "degC")
        print("Outlet Water Pressure:", regs[7] / 100.0, "Bar")
        print("Return Water Pressure:", regs[8] / 100.0, "Bar")
        print("Ambient Temp:", regs[9] / 10.0, "degC")
        print("Make-up Water Pump:", "ON" if regs[10] else "OFF")
        print("Fault Alarm Code:", regs[11])

except Exception as e:
    print("Read failed:", e)

client.close()
