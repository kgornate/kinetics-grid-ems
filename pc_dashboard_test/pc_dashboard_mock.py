"""
PC Mock Dashboard for EMS Gateway Testing.

Role of this file:
- Runs on PC/laptop.
- Receives live UDP telemetry from i.MX93 Gateway.
- Sends TCP commands to i.MX93 Gateway.
- Acts like a simple terminal-based dashboard before Flutter GUI.

Direction:

Telemetry:
    i.MX93 Gateway  --->  PC Dashboard Mock
    UDP port 5005

Commands:
    PC Dashboard Mock  --->  i.MX93 Gateway
    TCP port 6000

Run on PC:

    python pc_dashboard_test/pc_dashboard_mock.py --gateway-ip <IMX93_IP>

Example:

    python pc_dashboard_test/pc_dashboard_mock.py --gateway-ip 192.168.1.50
"""

import argparse
import json
import socket
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional


class PCDashboardMock:
    """
    Terminal-based PC mock dashboard.

    Features:
    - Background UDP listener for telemetry
    - Foreground command menu for TCP control
    - Stores latest telemetry packet
    """

    def __init__(
        self,
        gateway_ip: str,
        tcp_port: int = 6000,
        udp_listen_ip: str = "0.0.0.0",
        udp_listen_port: int = 5005,
        tcp_timeout_sec: float = 5.0,
    ):
        self.gateway_ip = gateway_ip
        self.tcp_port = int(tcp_port)
        self.udp_listen_ip = udp_listen_ip
        self.udp_listen_port = int(udp_listen_port)
        self.tcp_timeout_sec = float(tcp_timeout_sec)

        self.udp_socket: Optional[socket.socket] = None
        self.udp_thread: Optional[threading.Thread] = None

        self.running = False

        self.latest_udp_packet: Optional[Dict[str, Any]] = None
        self.latest_payload: Optional[Dict[str, Any]] = None
        self.latest_telemetry_data: Dict[str, Any] = {}

        self.total_udp_packets = 0
        self.last_udp_sender: Optional[str] = None
        self.last_udp_time: Optional[str] = None

        self._telemetry_lock = threading.Lock()

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
    # Start / Stop
    # -------------------------------------------------

    def start(self) -> None:
        """
        Start mock dashboard.
        """

        self.running = True
        self._start_udp_listener()

        print("\n====================================================")
        print("             PC EMS Mock Dashboard")
        print("====================================================")
        print(f"Gateway IP              : {self.gateway_ip}")
        print(f"TCP Command Port        : {self.tcp_port}")
        print(f"UDP Listen IP           : {self.udp_listen_ip}")
        print(f"UDP Listen Port         : {self.udp_listen_port}")
        print("====================================================")
        print("UDP telemetry listener started in background.")
        print("Use menu commands to send TCP commands to i.MX93.")
        print("====================================================\n")

        self._menu_loop()

    def stop(self) -> None:
        """
        Stop dashboard.
        """

        self.running = False

        if self.udp_socket is not None:
            try:
                self.udp_socket.close()
            except Exception:
                pass

            self.udp_socket = None

        if self.udp_thread is not None:
            self.udp_thread.join(timeout=2)

        print("\n[PC DASHBOARD] Stopped")

    # -------------------------------------------------
    # UDP Telemetry Listener
    # -------------------------------------------------

    def _start_udp_listener(self) -> None:
        """
        Start UDP telemetry listener in background thread.
        """

        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_socket.bind((self.udp_listen_ip, self.udp_listen_port))

        self.udp_thread = threading.Thread(
            target=self._udp_listener_loop,
            name="PCDashboardUDPListenerThread",
            daemon=True,
        )

        self.udp_thread.start()

    def _udp_listener_loop(self) -> None:
        """
        Background UDP receive loop.
        """

        while self.running:
            try:
                if self.udp_socket is None:
                    break

                data, sender = self.udp_socket.recvfrom(8192)

                message = data.decode("utf-8", errors="replace")
                packet = json.loads(message)

                self._store_udp_packet(packet, sender)

            except OSError:
                break

            except Exception as e:
                print(f"\n[UDP] Error receiving telemetry: {e}")

    def _store_udp_packet(self, packet: Dict[str, Any], sender) -> None:
        """
        Store latest telemetry packet safely.
        """

        payload = self._extract_payload(packet)
        telemetry_data = payload.get("data", {})

        with self._telemetry_lock:
            self.latest_udp_packet = packet
            self.latest_payload = payload
            self.latest_telemetry_data = telemetry_data
            self.total_udp_packets += 1
            self.last_udp_sender = f"{sender[0]}:{sender[1]}"
            self.last_udp_time = self._now()

    @staticmethod
    def _extract_payload(packet: Dict[str, Any]) -> Dict[str, Any]:
        """
        Supports both wrapped UDP streamer format and direct telemetry format.

        Wrapped format:
        {
            "streamer": "...",
            "sequence_number": 1,
            "payload": {
                "type": "telemetry",
                "data": {...}
            }
        }
        """

        if "payload" in packet and isinstance(packet["payload"], dict):
            return packet["payload"]

        return packet

    # -------------------------------------------------
    # TCP Command Client
    # -------------------------------------------------

    def send_tcp_command(
        self,
        command: str,
        value: Optional[Any] = None,
        verify: bool = True,
    ) -> Dict[str, Any]:
        """
        Send one TCP command to i.MX93 gateway.
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

        message = json.dumps(packet, default=str) + "\n"

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.tcp_timeout_sec)
                sock.connect((self.gateway_ip, self.tcp_port))
                sock.sendall(message.encode("utf-8"))

                response = self._receive_tcp_response(sock)

                return response

        except socket.timeout:
            return self._local_error_response(packet, "TCP timeout waiting for response")

        except ConnectionRefusedError:
            return self._local_error_response(
                packet,
                "Connection refused. Check if i.MX93 TCP server is running.",
            )

        except OSError as e:
            return self._local_error_response(packet, f"Socket error: {e}")

        except Exception as e:
            return self._local_error_response(packet, f"Unexpected error: {e}")

    @staticmethod
    def _receive_tcp_response(sock: socket.socket) -> Dict[str, Any]:
        """
        Receive newline-delimited JSON response.
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

    def _local_error_response(self, command_packet: Dict[str, Any], message: str) -> Dict[str, Any]:
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
    # Display
    # -------------------------------------------------

    def print_dashboard(self) -> None:
        """
        Print latest telemetry dashboard.
        """

        with self._telemetry_lock:
            payload = dict(self.latest_payload) if self.latest_payload else {}
            telemetry = dict(self.latest_telemetry_data)
            total_packets = self.total_udp_packets
            last_sender = self.last_udp_sender
            last_udp_time = self.last_udp_time
            raw_packet = dict(self.latest_udp_packet) if self.latest_udp_packet else {}

        print("\n====================================================")
        print("                LIVE CHILLER DASHBOARD")
        print("====================================================")
        print(f"Gateway IP              : {self.gateway_ip}")
        print(f"UDP Packets Received    : {total_packets}")
        print(f"Last UDP Sender         : {last_sender}")
        print(f"Last UDP Time           : {last_udp_time}")

        if raw_packet.get("sequence_number") is not None:
            print(f"UDP Sequence Number     : {raw_packet.get('sequence_number')}")

        print("----------------------------------------------------")
        print(f"Payload Type            : {payload.get('type')}")
        print(f"Gateway ID              : {payload.get('gateway_id')}")
        print(f"Asset ID                : {payload.get('asset_id')}")
        print(f"Gateway Timestamp       : {payload.get('timestamp')}")
        print(f"Gateway Status          : {payload.get('status')}")

        if payload.get("error"):
            print(f"Gateway Error           : {payload.get('error')}")

        print("----------------------------------------------------")
        print("Chiller Telemetry")
        print("----------------------------------------------------")

        if not telemetry:
            print("No telemetry received yet.")
            print("Make sure i.MX93 gateway is running and PC IP is correct.")
        else:
            print(f"Water Pump              : {telemetry.get('water_pump')}")
            print(f"Compressor 1            : {telemetry.get('compressor1')}")
            print(f"Compressor 2            : {telemetry.get('compressor2')}")
            print(f"Electric Heater         : {telemetry.get('electric_heater')}")
            print(f"Condensate Fan          : {telemetry.get('condensate_fan')}")
            print(f"Make-up Pump            : {telemetry.get('makeup_pump')}")
            print(f"Outlet Water Temp       : {telemetry.get('outlet_water_temp')} °C")
            print(f"Return Water Temp       : {telemetry.get('return_water_temp')} °C")
            print(f"Outlet Water Pressure   : {telemetry.get('outlet_water_pressure')} Bar")
            print(f"Return Water Pressure   : {telemetry.get('return_water_pressure')} Bar")
            print(f"Ambient Temp            : {telemetry.get('ambient_temp')} °C")
            print(f"Fault Code              : {telemetry.get('fault_code')}")
            print(f"Control Mode            : {telemetry.get('control_mode')}")
            print(f"Set Temperature         : {telemetry.get('set_temperature')}")
            print(f"Communication Status    : {telemetry.get('communication_status')}")

        print("====================================================\n")

    @staticmethod
    def print_response(response: Dict[str, Any]) -> None:
        """
        Print TCP command response.
        """

        print("\n================ COMMAND RESPONSE ==================")
        print(f"Type        : {response.get('type')}")
        print(f"Request ID  : {response.get('request_id')}")
        print(f"Timestamp   : {response.get('timestamp')}")
        print(f"Status      : {response.get('status')}")
        print(f"Command     : {response.get('command')}")
        print(f"Message     : {response.get('message')}")
        print("----------------------------------------------------")
        print(json.dumps(response, indent=2, default=str))
        print("====================================================\n")

    # -------------------------------------------------
    # Menu
    # -------------------------------------------------

    def _menu_loop(self) -> None:
        """
        Simple terminal menu.
        """

        while self.running:
            self._print_menu()

            user_input = input("Enter option: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["q", "quit", "exit"]:
                break

            self._handle_menu_input(user_input)

    @staticmethod
    def _print_menu() -> None:
        print("\n---------------- EMS PC MOCK DASHBOARD -------------")
        print("1  - Show latest telemetry dashboard")
        print("2  - Send READ_ALL")
        print("3  - Send READ_SETTINGS")
        print("4  - Send READ_MODE")
        print("5  - Send READ_TEMP")
        print("6  - Send READ_ONOFF")
        print("7  - Send SET_TEMP")
        print("8  - Send SET_MODE")
        print("9  - Send CHILLER_ON")
        print("10 - Send CHILLER_OFF")
        print("11 - Show raw latest telemetry JSON")
        print("q  - Quit")
        print("----------------------------------------------------")

    def _handle_menu_input(self, user_input: str) -> None:
        """
        Handle menu choice.
        """

        try:
            if user_input == "1":
                self.print_dashboard()

            elif user_input == "2":
                response = self.send_tcp_command("READ_ALL")
                self.print_response(response)

            elif user_input == "3":
                response = self.send_tcp_command("READ_SETTINGS")
                self.print_response(response)

            elif user_input == "4":
                response = self.send_tcp_command("READ_MODE")
                self.print_response(response)

            elif user_input == "5":
                response = self.send_tcp_command("READ_TEMP")
                self.print_response(response)

            elif user_input == "6":
                response = self.send_tcp_command("READ_ONOFF")
                self.print_response(response)

            elif user_input == "7":
                temp = input("Enter set temperature in °C, example 25.0: ").strip()
                response = self.send_tcp_command("SET_TEMP", value=float(temp))
                self.print_response(response)

            elif user_input == "8":
                print("\nMode options:")
                print("0 = Automatic")
                print("1 = Cooling / Refrigeration")
                print("2 = Heating")
                print("3 = Water pump circulation")
                mode = input("Enter mode value: ").strip()
                response = self.send_tcp_command("SET_MODE", value=mode)
                self.print_response(response)

            elif user_input == "9":
                confirm = input("Confirm CHILLER_ON? Type YES: ").strip()
                if confirm == "YES":
                    response = self.send_tcp_command("CHILLER_ON")
                    self.print_response(response)
                else:
                    print("CHILLER_ON cancelled")

            elif user_input == "10":
                confirm = input("Confirm CHILLER_OFF? Type YES: ").strip()
                if confirm == "YES":
                    response = self.send_tcp_command("CHILLER_OFF")
                    self.print_response(response)
                else:
                    print("CHILLER_OFF cancelled")

            elif user_input == "11":
                with self._telemetry_lock:
                    packet = self.latest_udp_packet

                print("\n---------------- RAW TELEMETRY JSON ----------------")
                print(json.dumps(packet, indent=2, default=str))
                print("----------------------------------------------------")

            else:
                print("Invalid option")

        except Exception as e:
            print(f"[PC DASHBOARD] Error: {e}")


# -------------------------------------------------
# CLI
# -------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PC Mock Dashboard for i.MX93 EMS Gateway"
    )

    parser.add_argument(
        "--gateway-ip",
        required=True,
        help="i.MX93 Gateway IP address",
    )

    parser.add_argument(
        "--tcp-port",
        type=int,
        default=6000,
        help="i.MX93 TCP command port. Default: 6000",
    )

    parser.add_argument(
        "--udp-ip",
        default="0.0.0.0",
        help="PC UDP listen IP. Default: 0.0.0.0",
    )

    parser.add_argument(
        "--udp-port",
        type=int,
        default=5005,
        help="PC UDP listen port. Default: 5005",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="TCP timeout in seconds. Default: 5",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    dashboard = PCDashboardMock(
        gateway_ip=args.gateway_ip,
        tcp_port=args.tcp_port,
        udp_listen_ip=args.udp_ip,
        udp_listen_port=args.udp_port,
        tcp_timeout_sec=args.timeout,
    )

    try:
        dashboard.start()

    except KeyboardInterrupt:
        print("\n[PC DASHBOARD] Ctrl+C received")

    finally:
        dashboard.stop()


if __name__ == "__main__":
    main()