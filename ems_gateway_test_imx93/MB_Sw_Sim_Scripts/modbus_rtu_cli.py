#!/usr/bin/env python3
"""
modbus_rtu_cli.py

Generic Modbus RTU command-line tool for FRDM i.MX93.

Use cases:
1. Read input registers      -> Function Code 04
2. Read holding registers    -> Function Code 03
3. Write single register     -> Function Code 06
4. Write multiple registers  -> Function Code 16

Example commands:

Read input registers:
python3 modbus_rtu_cli.py read-input --address 0 --count 12

Read holding registers:
python3 modbus_rtu_cli.py read-holding --address 200 --count 6

Write single holding register:
python3 modbus_rtu_cli.py write --address 201 --value 1

Write multiple holding registers:
python3 modbus_rtu_cli.py write-multiple --address 200 --values 0 1 0 0 0 250
"""

import argparse
import sys
import time

from pymodbus.client import ModbusSerialClient


def create_client(args):
    """
    Create Modbus RTU serial client.
    Default serial format:
    9600 baud, 8 data bits, no parity, 1 stop bit.
    """
    return ModbusSerialClient(
        port=args.port,
        baudrate=args.baudrate,
        bytesize=args.bytesize,
        parity=args.parity,
        stopbits=args.stopbits,
        timeout=args.timeout,
        retries=args.retries,
    )


def open_client(args):
    client = create_client(args)

    print("Opening Modbus RTU serial port")
    print("------------------------------")
    print(f"Port       : {args.port}")
    print(f"Slave ID   : {args.slave_id}")
    print(f"Baudrate   : {args.baudrate}")
    print(f"Data bits  : {args.bytesize}")
    print(f"Parity     : {args.parity}")
    print(f"Stop bits  : {args.stopbits}")
    print(f"Timeout    : {args.timeout} sec")
    print(f"Retries    : {args.retries}")
    print("")

    if not client.connect():
        print("ERROR: Failed to open serial port")
        sys.exit(1)

    return client


def print_registers(start_address, registers):
    print("")
    print("Received Registers")
    print("------------------")

    for index, value in enumerate(registers):
        address = start_address + index
        print(f"Address {address:<6} = {value}")


def read_holding(args):
    """
    Function Code 03: Read Holding Registers
    """
    client = open_client(args)

    try:
        time.sleep(args.delay)

        print("Request")
        print("-------")
        print("Function   : 03 Read Holding Registers")
        print(f"Address    : {args.address}")
        print(f"Count      : {args.count}")
        print("")

        result = client.read_holding_registers(
            address=args.address,
            count=args.count,
            device_id=args.slave_id,
        )

        if result.isError():
            print("ERROR: Modbus read holding registers failed")
            print(result)
        else:
            print_registers(args.address, result.registers)

    except Exception as exc:
        print("EXCEPTION:", exc)

    finally:
        client.close()


def read_input(args):
    """
    Function Code 04: Read Input Registers
    """
    client = open_client(args)

    try:
        time.sleep(args.delay)

        print("Request")
        print("-------")
        print("Function   : 04 Read Input Registers")
        print(f"Address    : {args.address}")
        print(f"Count      : {args.count}")
        print("")

        result = client.read_input_registers(
            address=args.address,
            count=args.count,
            device_id=args.slave_id,
        )

        if result.isError():
            print("ERROR: Modbus read input registers failed")
            print(result)
        else:
            print_registers(args.address, result.registers)

    except Exception as exc:
        print("EXCEPTION:", exc)

    finally:
        client.close()


def write_single(args):
    """
    Function Code 06: Write Single Holding Register
    """
    client = open_client(args)

    try:
        time.sleep(args.delay)

        print("Request")
        print("-------")
        print("Function   : 06 Write Single Holding Register")
        print(f"Address    : {args.address}")
        print(f"Value      : {args.value}")
        print("")

        result = client.write_register(
            address=args.address,
            value=args.value,
            device_id=args.slave_id,
        )

        if result.isError():
            print("ERROR: Modbus write single register failed")
            print(result)
        else:
            print("SUCCESS")
            print(f"Written value {args.value} to holding register {args.address}")

    except Exception as exc:
        print("EXCEPTION:", exc)

    finally:
        client.close()


def write_multiple(args):
    """
    Function Code 16: Write Multiple Holding Registers
    """
    client = open_client(args)

    values = [int(value) for value in args.values]

    try:
        time.sleep(args.delay)

        print("Request")
        print("-------")
        print("Function   : 16 Write Multiple Holding Registers")
        print(f"Address    : {args.address}")
        print(f"Values     : {values}")
        print("")

        result = client.write_registers(
            address=args.address,
            values=values,
            device_id=args.slave_id,
        )

        if result.isError():
            print("ERROR: Modbus write multiple registers failed")
            print(result)
        else:
            print("SUCCESS")
            print(f"Written values {values} starting from holding register {args.address}")

    except Exception as exc:
        print("EXCEPTION:", exc)

    finally:
        client.close()


def build_parser():
    parser = argparse.ArgumentParser(
        description="Generic Modbus RTU CLI tool for FRDM i.MX93"
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
        help="Modbus slave/device ID. Default: 1",
    )

    parser.add_argument(
        "--baudrate",
        type=int,
        default=9600,
        help="Baudrate. Default: 9600",
    )

    parser.add_argument(
        "--bytesize",
        type=int,
        default=8,
        choices=[7, 8],
        help="Data bits. Default: 8",
    )

    parser.add_argument(
        "--parity",
        default="N",
        choices=["N", "E", "O"],
        help="Parity: N=None, E=Even, O=Odd. Default: N",
    )

    parser.add_argument(
        "--stopbits",
        type=int,
        default=1,
        choices=[1, 2],
        help="Stop bits. Default: 1",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="Response timeout in seconds. Default: 2.0",
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
        help="Delay before Modbus command in seconds. Default: 0.2",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    read_holding_parser = subparsers.add_parser(
        "read-holding",
        help="Read holding registers. Function Code 03",
    )
    read_holding_parser.add_argument("--address", type=int, required=True)
    read_holding_parser.add_argument("--count", type=int, required=True)
    read_holding_parser.set_defaults(func=read_holding)

    read_input_parser = subparsers.add_parser(
        "read-input",
        help="Read input registers. Function Code 04",
    )
    read_input_parser.add_argument("--address", type=int, required=True)
    read_input_parser.add_argument("--count", type=int, required=True)
    read_input_parser.set_defaults(func=read_input)

    write_single_parser = subparsers.add_parser(
        "write",
        help="Write single holding register. Function Code 06",
    )
    write_single_parser.add_argument("--address", type=int, required=True)
    write_single_parser.add_argument("--value", type=int, required=True)
    write_single_parser.set_defaults(func=write_single)

    write_multiple_parser = subparsers.add_parser(
        "write-multiple",
        help="Write multiple holding registers. Function Code 16",
    )
    write_multiple_parser.add_argument("--address", type=int, required=True)
    write_multiple_parser.add_argument(
        "--values",
        nargs="+",
        required=True,
        help="Space-separated register values",
    )
    write_multiple_parser.set_defaults(func=write_multiple)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()