#!/usr/bin/env python3

import argparse
import sys

try:
    # pymodbus 3.x
    from pymodbus.client import ModbusTcpClient
except ImportError:
    # pymodbus 2.x fallback
    from pymodbus.client.sync import ModbusTcpClient


def read_holding_registers(client, address: int, count: int, unit_id: int):
    """
    Compatible read helper for different pymodbus versions.

    Newer pymodbus versions use:
        device_id

    Older pymodbus versions may use:
        slave
        unit
    """
    try:
        return client.read_holding_registers(
            address=address,
            count=count,
            device_id=unit_id,
        )
    except TypeError:
        try:
            return client.read_holding_registers(
                address=address,
                count=count,
                slave=unit_id,
            )
        except TypeError:
            try:
                return client.read_holding_registers(
                    address=address,
                    count=count,
                    unit=unit_id,
                )
            except TypeError:
                return client.read_holding_registers(
                    address=address,
                    count=count,
                )


def write_single_register(client, address: int, value: int, unit_id: int):
    """
    Compatible write helper for different pymodbus versions.

    Newer pymodbus versions use:
        device_id

    Older pymodbus versions may use:
        slave
        unit
    """
    try:
        return client.write_register(
            address=address,
            value=value,
            device_id=unit_id,
        )
    except TypeError:
        try:
            return client.write_register(
                address=address,
                value=value,
                slave=unit_id,
            )
        except TypeError:
            try:
                return client.write_register(
                    address=address,
                    value=value,
                    unit=unit_id,
                )
            except TypeError:
                return client.write_register(
                    address=address,
                    value=value,
                )


def check_response(response, operation_name: str):
    """
    Common response validation.
    """
    if response is None:
        print(f"ERROR: No response received during {operation_name}.")
        sys.exit(1)

    if hasattr(response, "isError") and response.isError():
        print(f"ERROR: Modbus exception received during {operation_name}.")
        print(response)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Simple Modbus TCP Client for FRDM i.MX93 EMS validation"
    )

    parser.add_argument(
        "--host",
        required=True,
        help="Modbus TCP server IP address, example: 192.168.10.1",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=502,
        help="Modbus TCP port, default: 502",
    )

    parser.add_argument(
        "--unit",
        type=int,
        default=1,
        help="Modbus Unit ID / Slave ID / Device ID, default: 1",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    read_parser = subparsers.add_parser(
        "read",
        help="Read holding registers",
    )

    read_parser.add_argument(
        "--address",
        type=int,
        required=True,
        help="0-based holding register address. Example: ModSim 40001 = address 0",
    )

    read_parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of registers to read",
    )

    write_parser = subparsers.add_parser(
        "write",
        help="Write single holding register",
    )

    write_parser.add_argument(
        "--address",
        type=int,
        required=True,
        help="0-based holding register address. Example: ModSim 40005 = address 4",
    )

    write_parser.add_argument(
        "--value",
        type=int,
        required=True,
        help="Value to write",
    )

    args = parser.parse_args()

    print("======================================")
    print(" Modbus TCP Client - i.MX93 EMS Test")
    print("======================================")
    print(f"Server IP   : {args.host}")
    print(f"Server Port : {args.port}")
    print(f"Unit ID     : {args.unit}")
    print(f"Command     : {args.command}")
    print("--------------------------------------")

    client = ModbusTcpClient(
        host=args.host,
        port=args.port,
        timeout=3,
    )

    connected = client.connect()

    if not connected:
        print("ERROR: Could not connect to Modbus TCP server.")
        print("Check:")
        print("1. PC IP address")
        print("2. ModSim TCP server mode")
        print("3. Port 502")
        print("4. Windows Firewall")
        print("5. Ethernet connectivity between PC and i.MX93")
        sys.exit(1)

    print("Connected successfully.")

    try:
        if args.command == "read":
            print(
                f"Reading holding registers from address {args.address}, "
                f"count {args.count}"
            )

            response = read_holding_registers(
                client=client,
                address=args.address,
                count=args.count,
                unit_id=args.unit,
            )

            check_response(response, "read holding registers")

            if not hasattr(response, "registers"):
                print("ERROR: Response does not contain register data.")
                print(response)
                sys.exit(1)

            print("Read successful.")
            print("--------------------------------------")

            for index, value in enumerate(response.registers):
                actual_address = args.address + index
                modsim_display_address = 40001 + actual_address

                print(
                    f"Address {actual_address:05d} "
                    f"(ModSim approx {modsim_display_address}) = {value}"
                )

        elif args.command == "write":
            print(
                f"Writing value {args.value} "
                f"to holding register address {args.address}"
            )

            response = write_single_register(
                client=client,
                address=args.address,
                value=args.value,
                unit_id=args.unit,
            )

            check_response(response, "write single register")

            print("Write successful.")
            print(f"Written address {args.address} = {args.value}")
            print("--------------------------------------")

            print("Reading back for verification...")

            verify = read_holding_registers(
                client=client,
                address=args.address,
                count=1,
                unit_id=args.unit,
            )

            check_response(verify, "readback verification")

            if not hasattr(verify, "registers"):
                print("ERROR: Readback response does not contain register data.")
                print(verify)
                sys.exit(1)

            readback_value = verify.registers[0]

            print(f"Readback value = {readback_value}")

            if readback_value == args.value:
                print("Verification PASSED.")
            else:
                print("Verification FAILED.")
                print(f"Expected {args.value}, got {readback_value}")
                sys.exit(1)

    finally:
        client.close()
        print("Connection closed.")


if __name__ == "__main__":
    main()