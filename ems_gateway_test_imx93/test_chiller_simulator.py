from pymodbus.client import ModbusSerialClient
import time

PORT = "/dev/ttyUSB0"
SLAVE_ID = 1

client = ModbusSerialClient(
    port=PORT,
    baudrate=9600,
    bytesize=8,
    parity="N",
    stopbits=1,
    timeout=1
)

if not client.connect():
    print("Failed to open Modbus RTU port")
    exit(1)

def read_live_data():
    time.sleep(0.2)

    result = client.read_input_registers(
        address=0,
        count=12,
        slave=SLAVE_ID
    )

    if result.isError():
        print("Read live data error:", result)
        return

    regs = result.registers

    print("\nLive Chiller Data")
    print("-----------------")
    print("Water Pump:", "RUNNING" if regs[0] else "STOPPED")
    print("Compressor 1:", "RUNNING" if regs[1] else "STOPPED")
    print("Compressor 2:", "RUNNING" if regs[2] else "STOPPED")
    print("Electric Heater:", "RUNNING" if regs[3] else "STOPPED")
    print("Condensate Fan:", "RUNNING" if regs[4] else "STOPPED")
    print("Outlet Water Temp:", regs[5] / 10.0, "°C")
    print("Return Water Temp:", regs[6] / 10.0, "°C")
    print("Outlet Water Pressure:", regs[7] / 100.0, "Bar")
    print("Return Water Pressure:", regs[8] / 100.0, "Bar")
    print("Ambient Temp:", regs[9] / 10.0, "°C")
    print("Make-up Water Pump:", "ON" if regs[10] else "OFF")
    print("Fault Alarm Code:", regs[11])

def read_control_registers():
    time.sleep(0.2)

    result = client.read_holding_registers(
        address=200,
        count=6,
        slave=SLAVE_ID
    )

    if result.isError():
        print("Read control register error:", result)
        return

    regs = result.registers

    print("\nControl Registers")
    print("-----------------")
    print("Control Mode Register 200:", regs[0])
    print("System ON/OFF Register 201:", regs[1])
    print("Set Temperature Register 205:", regs[5] / 10.0, "°C")

def write_system_on_off(value):
    time.sleep(0.2)

    result = client.write_register(
        address=201,
        value=value,
        slave=SLAVE_ID
    )

    if result.isError():
        print("Write ON/OFF error:", result)
    else:
        print(f"Written System ON/OFF register 201 = {value}")

def write_set_temperature(temp_c):
    raw = int(temp_c * 10)

    time.sleep(0.2)

    result = client.write_register(
        address=205,
        value=raw,
        slave=SLAVE_ID
    )

    if result.isError():
        print("Write set temperature error:", result)
    else:
        print(f"Written Set Temperature register 205 = {raw} ({temp_c} °C)")

read_live_data()
read_control_registers()

write_system_on_off(1)
write_set_temperature(25.0)

read_control_registers()

client.close()