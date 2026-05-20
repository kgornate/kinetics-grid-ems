"""
PC TCP Client for EMS Gateway Testing.

Role of this file:
- Runs on PC/laptop.
- Sends TCP commands to i.MX93 Gateway.
- Receives ACK/NACK response from i.MX93.
- Used before Flutter GUI development.

Direction:
    PC Dashboard Test  --->  i.MX93 Gateway

Protocol:
- TCP
- JSON command format
- Newline-delimited JSON

Example commands:

    python pc_dashboard_test/pc_tcp_client.py --gateway-ip 192.168.1.50 READ_ALL
    python pc_dashboard_test/pc_tcp_client.py --gateway-ip 192.168.1.50 READ_MODE
    python pc_dashboard_test/pc_tcp_client.py --gateway-ip 192.168.1.50 SET_TEMP 25.0
    python pc_dashboard_test/pc_tcp_client.py --gateway-ip 192.168.1.50 SET_MODE 1
    python pc_dashboard_test/pc_tcp_client.py --gateway-ip 192.168.1.50 CHILLER_ON
    python pc_dashboard_test/pc_tcp_client.py --gateway-ip 192.168.1.50 CHILLER_OFF
"""

import argparse
import json
import socket
import uuid
from datetime import datetime
from typing import Any, Dict, Optional


class PCTCPClient:
    """
    PC-side TCP client for sending commands to i.MX93 Gateway.
    """

    def __init__(
        self,
        gateway_ip: str,
        gateway_port: int = 6000,
        timeout_sec: float = 5.0,
    ):
        self.gateway_ip = gateway_ip
        self.gateway_port = int(gateway_port)
        self.timeout_sec = float(timeout_sec)

    # -------------------------------------------------
    # Utility
    # -------------------------------------------------

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _generate_request_id() -> str:
        return "REQ_" + uuid.uuid4().hex[:8].upper()

    # -------------------------------------------------
    # Command Packet Creation
    # -------------------------------------------------

    def create_command_packet(
        self,
        command: str,
        value: Optional[Any] = None,
        verify: bool = True,
    ) -> Dict[str, Any]:
        """
        Create JSON command packet.
        """

        packet: Dict[str, Any] = {
            "type": "command",
            "request_id": self._generate_request_id(),
            "timestamp": self._now(),
            "command": command.strip().upper(),
            "verify": verify,
        }

        if value is not None:
            packet["value"] = value

        return packet

    # -------------------------------------------------
    # TCP Send / Receive
    # -------------------------------------------------

    def send_command(
        self,
        command: str,
        value: Optional[Any] = None,
        verify: bool = True,
    ) -> Dict[str, Any]:
        """
        Send command to i.MX93 Gateway and receive response.
        """

        command_packet = self.create_command_packet(
            command=command,
            value=value,
            verify=verify,
        )

        message = json.dumps(command_packet, default=str) + "\n"

        print("\n================ TCP COMMAND SEND ==================")
        print(f"Gateway IP          : {self.gateway_ip}")
        print(f"Gateway Port        : {self.gateway_port}")
        print(f"Command             : {command_packet.get('command')}")
        print(f"Value               : {command_packet.get('value')}")
        print(f"Request ID          : {command_packet.get('request_id')}")
        print("----------------------------------------------------")
        print("Raw JSON:")
        print(json.dumps(command_packet, indent=2, default=str))
        print("====================================================")

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout_sec)

                print(f"\n[PC TCP] Connecting to {self.gateway_ip}:{self.gateway_port}...")
                sock.connect((self.gateway_ip, self.gateway_port))
                print("[PC TCP] Connected")

                print("[PC TCP] Sending command...")
                sock.sendall(message.encode("utf-8"))

                response = self._receive_response(sock)

                print("[PC TCP] Response received")

                return response

        except socket.timeout:
            return self._error_response(command_packet, "TCP timeout waiting for response")

        except ConnectionRefusedError:
            return self._error_response(
                command_packet,
                "Connection refused. Check if i.MX93 TCP server is running.",
            )

        except OSError as e:
            return self._error_response(command_packet, f"Socket error: {e}")

        except Exception as e:
            return self._error_response(command_packet, f"Unexpected error: {e}")

    def _receive_response(self, sock: socket.socket) -> Dict[str, Any]:
        """
        Receive newline-delimited JSON response from server.
        """

        buffer = ""

        while True:
            data = sock.recv(4096)

            if not data:
                raise RuntimeError("Connection closed before response received")

            buffer += data.decode("utf-8", errors="replace")

            if "\n" in buffer:
                line, _ = buffer.split("\n", 1)
                line = line.strip()

                if not line:
                    continue

                return json.loads(line)

    def _error_response(self, command_packet: Dict[str, Any], message: str) -> Dict[str, Any]:
        """
        Create local error response if TCP communication fails.
        """

        return {
            "type": "local_error",
            "request_id": command_packet.get("request_id"),
            "timestamp": self._now(),
            "status": "error",
            "command": command_packet.get("command"),
            "message": message,
            "data": {},
        }


# -------------------------------------------------
# Print Helpers
# -------------------------------------------------

def print_response(response: Dict[str, Any]) -> None:
    """
    Print gateway response in readable format.
    """

    print("\n================ TCP RESPONSE RECEIVED =============")
    print(f"Type                : {response.get('type')}")
    print(f"Request ID          : {response.get('request_id')}")
    print(f"Timestamp           : {response.get('timestamp')}")
    print(f"Status              : {response.get('status')}")
    print(f"Command             : {response.get('command')}")
    print(f"Message             : {response.get('message')}")
    print("----------------------------------------------------")
    print("Full Response JSON:")
    print(json.dumps(response, indent=2, default=str))
    print("====================================================")


# -------------------------------------------------
# CLI Parsing
# -------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PC TCP Client for i.MX93 EMS Gateway"
    )

    parser.add_argument(
        "--gateway-ip",
        required=True,
        help="i.MX93 Gateway IP address",
    )

    parser.add_argument(
        "--gateway-port",
        type=int,
        default=6000,
        help="i.MX93 Gateway TCP command port. Default: 6000",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="TCP timeout in seconds. Default: 5",
    )

    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Disable verification/readback for write commands",
    )

    parser.add_argument(
        "command",
        help=(
            "Command to send: READ_ALL, READ_SETTINGS, READ_MODE, READ_TEMP, "
            "READ_ONOFF, SET_TEMP, SET_MODE, CHILLER_ON, CHILLER_OFF"
        ),
    )

    parser.add_argument(
        "value",
        nargs="?",
        help="Value for SET_TEMP or SET_MODE",
    )

    return parser.parse_args()


def normalize_command_and_value(args: argparse.Namespace):
    """
    Validate and normalize command/value from CLI.
    """

    command = args.command.strip().upper()
    value = args.value

    allowed_commands = {
        "READ_ALL",
        "READ_SETTINGS",
        "READ_MODE",
        "READ_TEMP",
        "READ_ONOFF",
        "SET_TEMP",
        "SET_MODE",
        "CHILLER_ON",
        "CHILLER_OFF",
    }

    if command not in allowed_commands:
        raise ValueError(
            f"Unsupported command: {command}. "
            f"Allowed commands: {', '.join(sorted(allowed_commands))}"
        )

    if command == "SET_TEMP":
        if value is None:
            raise ValueError("SET_TEMP requires value, example: SET_TEMP 25.0")
        value = float(value)

    elif command == "SET_MODE":
        if value is None:
            raise ValueError("SET_MODE requires value, example: SET_MODE 1")
        value = value

    else:
        value = None

    verify = not args.no_verify

    return command, value, verify


# -------------------------------------------------
# Main
# -------------------------------------------------

def main() -> None:
    args = parse_args()

    try:
        command, value, verify = normalize_command_and_value(args)

        client = PCTCPClient(
            gateway_ip=args.gateway_ip,
            gateway_port=args.gateway_port,
            timeout_sec=args.timeout,
        )

        response = client.send_command(
            command=command,
            value=value,
            verify=verify,
        )

        print_response(response)

    except Exception as e:
        print(f"\n[PC TCP] Error: {e}")


if __name__ == "__main__":
    main()