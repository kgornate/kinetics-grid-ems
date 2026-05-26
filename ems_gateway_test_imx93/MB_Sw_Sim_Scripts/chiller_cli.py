#!/usr/bin/env python3
"""
chiller_cli.py

Chiller / Liquid Cooling System Modbus RTU CLI for FRDM i.MX93.

This script is designed for testing:
1. PC-based Modbus Slave simulator acting as fake chiller
2. Real liquid cooling/chiller controller over RS485 Modbus RTU

Communication default:
- Port      : /dev/ttyUSB0
- Slave ID  : 1
- Baudrate  : 9600
- Data bits : 8
- Parity    : None
- Stop bits : 1

Chiller register map:

Live data:
Function Code 04 - Read Input Registers
Address 0  : Water pump running state
Address 1  : Compressor 1 running status
Address 2  : Compressor 2 running status
Address 3  : Electric heater running status
Address 4  : Condensate fan running status
Address 5  : Outlet water temperature, scaling 0.1 degC
Address 6  : Return water temperature, scaling 0.1 degC
Address 7  : Outlet water pressure, scaling 0.01 Bar
Address 8  : Return water pressure, scaling 0.01 Bar
Address 9  : External ambient temperature, scaling 0.1 degC
Address 10 : Make-up water pump status
Address 11 : Fault alarm code

Control/settings:
Function Code 03 - Read Holding Registers
Function Code 06 - Write Single Holding Register
Function Code 16 - Write Multiple Holding Registers

Address 200 : Liquid cooling system control mode
Address 201 : System ON/OFF enable, 0=OFF, 1=ON
Address 205 : Unit setting temperature, scaling 0.1 degC

Example commands:

Read live data:
python3 chiller_cli.py read-live

Read control registers:
python3 chiller_cli.py read-control

Turn system ON:
python3 chiller_cli.py on

Turn system OFF:
python3 chiller_cli.py off

Set temperature:
python3 chiller_cli.py set-temp --temp 25.0

Set control mode:
python3 chiller_cli.py set-mode --mode 0

Write all control registers:
python3 chiller_cli.py write-all --mode 0 --system 1 --temp 25.0
"""

import argparse
import sys
import time

from pymodbus.client import ModbusSerialClient


REG_CONTROL_MODE = 200
REG_SYSTEM_ON_OFF = 201
REG_SET_TEMPERATURE = 205


def create_client(args):
    return ModbusSerialClient(
        port=args.port,
        baudrate=args.baudrate,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=args.timeout,
        retries=args.retries,
    )


def open_client(args):
    client = create_client(args)

    print("Opening Chiller Modbus RTU Connection")
    print("-------------------------------------")
    print(f"Port      : {args.port}")
    print(f"Slave ID  : {args.slave_id}")
    print(f"Baudrate  : {args.baudrate}")
    print("Format    : 8N1")
    print(f"Timeout   : {args.timeout} sec")
    print(f"Retries   : {args.retries}")
    print("")

    if not client.connect():
        print("ERROR: Failed to open serial port")
        sys.exit(1)

    return client


def decode_status(value):
    return "RUNNING" if value else "STOPPED"


def decode_on_off(value):
    return "ON" if value else "OFF"


def read_live(args):
    """
    Read live chiller data.
    Function Code 04.
    Input register address 0 to 11.
    """
    client = open_client(args)

    try:
        time.sleep(args.delay)

        result = client.read_input_registers(
            address=0,
            count=12,
            device_id=args.slave_id,
        )

        if result.isError():
            print("ERROR: Failed to read live chiller data")
            print(result)
            return

        regs = result.registers

        water_pump_state = regs[0]
        compressor1_state = regs[1]
        compressor2_state = regs[2]
        electric_heater_state = regs[3]
        condensate_fan_state = regs[4]

        outlet_water_temp = regs[5] / 10.0
        return_water_temp = regs[6] / 10.0

        outlet_water_pressure = regs[7] / 100.0
        return_water_pressure = regs[8] / 100.0

        ambient_temp = regs[9] / 10.0
        makeup_water_pump = regs[10]
        fault_alarm_code = regs[11]

        print("Live Chiller Data")
        print("-----------------")
        print("Water Pump             :", decode_status(water_pump_state))
        print("Compressor 1           :", decode_status(compressor1_state))
        print("Compressor 2           :", decode_status(compressor2_state))
        print("Electric Heater        :", decode_status(electric_heater_state))
        print("Condensate Fan         :", decode_status(condensate_fan_state))
        print("Outlet Water Temp      :", outlet_water_temp, "degC")
        print("Return Water Temp      :", return_water_temp, "degC")
        print("Outlet Water Pressure  :", outlet_water_pressure, "Bar")
        print("Return Water Pressure  :", return_water_pressure, "Bar")
        print("Ambient Temp           :", ambient_temp, "degC")
        print("Make-up Water Pump     :", decode_on_off(makeup_water_pump))
        print("Fault Alarm Code       :", fault_alarm_code)

        print("")
        print("Raw Input Registers 0-11")
        print("------------------------")
        for index, value in enumerate(regs):
            print(f"Address {index:<2} = {value}")

    except Exception as exc:
        print("EXCEPTION:", exc)

    finally:
        client.close()


def read_control(args):
    """
    Read chiller control/settings registers.
    Function Code 03.
    Holding register address 200 to 205.
    """
    client = open_client(args)

    try:
        time.sleep(args.delay)

        result = client.read_holding_registers(
            address=REG_CONTROL_MODE,
            count=6,
            device_id=args.slave_id,
        )

        if result.isError():
            print("ERROR: Failed to read chiller control registers")
            print(result)
            return

        regs = result.registers

        control_mode = regs[0]
        system_on_off = regs[1]
        set_temp_raw = regs[5]
        set_temp_c = set_temp_raw / 10.0

        print("Chiller Control Registers")
        print("-------------------------")
        print("Register 200 Control Mode  :", control_mode)
        print("Register 201 System ON/OFF :", system_on_off, f"({decode_on_off(system_on_off)})")
        print("Register 205 Set Temp      :", set_temp_raw, "=", set_temp_c, "degC")

        print("")
        print("Raw Holding Registers 200-205")
        print("-----------------------------")
        for index, value in enumerate(regs):
            address = REG_CONTROL_MODE + index
            print(f"Address {address} = {value}")

    except Exception as exc:
        print("EXCEPTION:", exc)

    finally:
        client.close()


def write_single_register(args, address, value, description):
    """
    Generic helper for writing one holding register.
    Function Code 06.
    """
    client = open_client(args)

    try:
        time.sleep(args.delay)

        print("Write Request")
        print("-------------")
        print("Function    : 06 Write Single Holding Register")
        print(f"Register    : {address}")
        print(f"Value       : {value}")
        print(f"Description : {description}")
        print("")

        result = client.write_register(
            address=address,
            value=value,
            device_id=args.slave_id,
        )

        if result.isError():
            print("ERROR: Write failed")
            print(result)
        else:
            print("SUCCESS:", description)
            print(f"Register {address} written with value {value}")

    except Exception as exc:
        print("EXCEPTION:", exc)

    finally:
        client.close()


def system_on(args):
    """
    Write register 201 = 1.
    """
    write_single_register(
        args=args,
        address=REG_SYSTEM_ON_OFF,
        value=1,
        description="System ON command",
    )


def system_off(args):
    """
    Write register 201 = 0.
    """
    write_single_register(
        args=args,
        address=REG_SYSTEM_ON_OFF,
        value=0,
        description="System OFF command",
    )


def set_temp(args):
    """
    Write register 205 with temperature scaling 0.1 degC.
    Example:
    25.0 degC -> 250
    27.5 degC -> 275
    """
    raw_value = int(round(args.temp * 10))

    write_single_register(
        args=args,
        address=REG_SET_TEMPERATURE,
        value=raw_value,
        description=f"Set temperature {args.temp} degC",
    )


def set_mode(args):
    """
    Write register 200 with selected control mode.
    Mode values depend on chiller protocol/vendor behavior.
    """
    write_single_register(
        args=args,
        address=REG_CONTROL_MODE,
        value=args.mode,
        description=f"Set control mode {args.mode}",
    )


def write_all(args):
    """
    Write registers 200 to 205 in one Modbus command.
    Function Code 16.

    Address 200 = Control mode
    Address 201 = System ON/OFF
    Address 202 = Reserved
    Address 203 = Reserved
    Address 204 = Reserved
    Address 205 = Set temperature
    """
    raw_temp = int(round(args.temp * 10))

    values = [
        args.mode,
        args.system,
        0,
        0,
        0,
        raw_temp,
    ]

    client = open_client(args)

    try:
        time.sleep(args.delay)

        print("Write Multiple Request")
        print("----------------------")
        print("Function    : 16 Write Multiple Holding Registers")
        print("Start Addr  : 200")
        print(f"Values      : {values}")
        print(f"Mode        : {args.mode}")
        print(f"System      : {args.system} ({decode_on_off(args.system)})")
        print(f"Set Temp    : {raw_temp} = {args.temp} degC")
        print("")

        result = client.write_registers(
            address=REG_CONTROL_MODE,
            values=values,
            device_id=args.slave_id,
        )

        if result.isError():
            print("ERROR: Write multiple registers failed")
            print(result)
        else:
            print("SUCCESS: Registers 200 to 205 written")
            print("Register 200 Control Mode  :", args.mode)
            print("Register 201 System ON/OFF :", args.system, f"({decode_on_off(args.system)})")
            print("Register 205 Set Temp      :", raw_temp, "=", args.temp, "degC")

    except Exception as exc:
        print("EXCEPTION:", exc)

    finally:
        client.close()


def demo_sequence(args):
    """
    Demo sequence:
    1. Read live data
    2. Read control
    3. Turn system OFF
    4. Turn system ON
    5. Set temperature
    6. Read control again
    """
    print("")
    print("========== DEMO: READ LIVE ==========")
    read_live(args)

    print("")
    print("========== DEMO: READ CONTROL BEFORE WRITE ==========")
    read_control(args)

    print("")
    print("========== DEMO: WRITE SYSTEM OFF ==========")
    write_single_register(
        args=args,
        address=REG_SYSTEM_ON_OFF,
        value=0,
        description="Demo: System OFF",
    )

    time.sleep(1)

    print("")
    print("========== DEMO: WRITE SYSTEM ON ==========")
    write_single_register(
        args=args,
        address=REG_SYSTEM_ON_OFF,
        value=1,
        description="Demo: System ON",
    )

    time.sleep(1)

    raw_temp = int(round(args.temp * 10))

    print("")
    print(f"========== DEMO: WRITE SET TEMP {args.temp} degC ==========")
    write_single_register(
        args=args,
        address=REG_SET_TEMPERATURE,
        value=raw_temp,
        description=f"Demo: Set temperature {args.temp} degC",
    )

    print("")
    print("========== DEMO: READ CONTROL AFTER WRITE ==========")
    read_control(args)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Chiller / Liquid Cooling Modbus RTU CLI for FRDM i.MX93"
    )

    parser.add_argument(
        "--port",
        default="/dev/ttyUSB0",
        help="Serial port. Default: /dev/ttyUSB0",
    )

    parser.add_argument(
        "--slave-id",
        type=int,
        default=1,
        help="Modbus slave ID. Default: 1",
    )

    parser.add_argument(
        "--baudrate",
        type=int,
        default=9600,
        help="Baudrate. Default: 9600",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="Timeout in seconds. Default: 2.0",
    )

    parser.add_argument(
        "--retries",
        type=int,
        default=1,
        help="Retry count. Default: 1",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Delay before command in seconds. Default: 0.2",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    read_live_parser = subparsers.add_parser(
        "read-live",
        help="Read live chiller data: input registers 0-11, function code 04",
    )
    read_live_parser.set_defaults(func=read_live)

    read_control_parser = subparsers.add_parser(
        "read-control",
        help="Read control registers 200-205, function code 03",
    )
    read_control_parser.set_defaults(func=read_control)

    on_parser = subparsers.add_parser(
        "on",
        help="Write system ON: register 201 = 1",
    )
    on_parser.set_defaults(func=system_on)

    off_parser = subparsers.add_parser(
        "off",
        help="Write system OFF: register 201 = 0",
    )
    off_parser.set_defaults(func=system_off)

    temp_parser = subparsers.add_parser(
        "set-temp",
        help="Write set temperature: register 205 = temp * 10",
    )
    temp_parser.add_argument(
        "--temp",
        type=float,
        required=True,
        help="Temperature in degC. Example: 25.0",
    )
    temp_parser.set_defaults(func=set_temp)

    mode_parser = subparsers.add_parser(
        "set-mode",
        help="Write control mode register 200",
    )
    mode_parser.add_argument(
        "--mode",
        type=int,
        required=True,
        help="Control mode value",
    )
    mode_parser.set_defaults(func=set_mode)

    write_all_parser = subparsers.add_parser(
        "write-all",
        help="Write registers 200-205 together",
    )
    write_all_parser.add_argument(
        "--mode",
        type=int,
        required=True,
        help="Control mode value",
    )
    write_all_parser.add_argument(
        "--system",
        type=int,
        choices=[0, 1],
        required=True,
        help="System state: 0=OFF, 1=ON",
    )
    write_all_parser.add_argument(
        "--temp",
        type=float,
        required=True,
        help="Set temperature in degC",
    )
    write_all_parser.set_defaults(func=write_all)

    demo_parser = subparsers.add_parser(
        "demo",
        help="Run read/write demo sequence",
    )
    demo_parser.add_argument(
        "--temp",
        type=float,
        default=25.0,
        help="Temperature to write during demo. Default: 25.0",
    )
    demo_parser.set_defaults(func=demo_sequence)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()