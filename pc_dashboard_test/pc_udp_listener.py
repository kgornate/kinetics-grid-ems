"""
PC UDP Listener for EMS Gateway Testing.

Role of this file:
- Runs on PC/laptop.
- Listens for UDP telemetry packets from i.MX93 Gateway.
- Receives chiller telemetry sent by udp_telemetry_streamer.py.
- Prints telemetry in readable format.

Direction:
    i.MX93 Gateway  --->  PC Dashboard Test

Protocol:
- UDP
- JSON packet

Default UDP Port:
    5005

Run on PC:
    python pc_dashboard_test/pc_udp_listener.py

Optional:
    python pc_dashboard_test/pc_udp_listener.py --port 5005
"""

import argparse
import json
import socket
from datetime import datetime
from typing import Any, Dict, Optional


class PCUDPListener:
    """
    UDP listener for PC-side EMS dashboard testing.
    """

    def __init__(
        self,
        listen_ip: str = "0.0.0.0",
        listen_port: int = 5005,
        buffer_size: int = 8192,
    ):
        self.listen_ip = listen_ip
        self.listen_port = int(listen_port)
        self.buffer_size = int(buffer_size)

        self.sock: Optional[socket.socket] = None

        self.total_packets = 0
        self.last_sender = None
        self.last_packet_time = None

    # -------------------------------------------------
    # Utility
    # -------------------------------------------------

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    # -------------------------------------------------
    # Socket Handling
    # -------------------------------------------------

    def start(self) -> None:
        """
        Start UDP listener.
        """

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Allows quick restart.
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.sock.bind((self.listen_ip, self.listen_port))

        print("====================================================")
        print("              PC UDP Telemetry Listener")
        print("====================================================")
        print(f"Listening IP       : {self.listen_ip}")
        print(f"Listening Port     : {self.listen_port}")
        print("Waiting for telemetry from i.MX93 Gateway...")
        print("Press Ctrl+C to stop")
        print("====================================================\n")

        self._listen_loop()

    def stop(self) -> None:
        """
        Stop UDP listener.
        """

        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass

            self.sock = None

        print("\n[PC UDP] Listener stopped")

    # -------------------------------------------------
    # Main Loop
    # -------------------------------------------------

    def _listen_loop(self) -> None:
        """
        Receive UDP packets forever.
        """

        if self.sock is None:
            raise RuntimeError("Socket not created")

        while True:
            data, sender = self.sock.recvfrom(self.buffer_size)

            self.total_packets += 1
            self.last_sender = f"{sender[0]}:{sender[1]}"
            self.last_packet_time = self._now()

            self._process_packet(data, sender)

    # -------------------------------------------------
    # Packet Processing
    # -------------------------------------------------

    def _process_packet(self, data: bytes, sender) -> None:
        """
        Decode and print UDP packet.
        """

        try:
            message = data.decode("utf-8", errors="replace")
            packet = json.loads(message)

            self._print_packet(packet, sender)

        except json.JSONDecodeError:
            print("\n[PC UDP] Non-JSON packet received")
            print(f"From : {sender[0]}:{sender[1]}")
            print(f"Raw  : {data}")

        except Exception as e:
            print(f"\n[PC UDP] Error while processing packet: {e}")

    def _extract_payload(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        """
        UDP streamer sends packet in this format:

        {
            "streamer": "...",
            "sequence_number": 1,
            "sent_timestamp": "...",
            "payload": {
                "type": "telemetry",
                "gateway_id": "...",
                "asset_id": "...",
                "data": {...}
            }
        }

        But this function also supports direct telemetry packet format.
        """

        if "payload" in packet and isinstance(packet["payload"], dict):
            return packet["payload"]

        return packet

    def _print_packet(self, packet: Dict[str, Any], sender) -> None:
        """
        Print packet in readable dashboard-style format.
        """

        payload = self._extract_payload(packet)

        telemetry_data = payload.get("data", {})

        print("\n================ TELEMETRY RECEIVED ================")
        print(f"Packet Count        : {self.total_packets}")
        print(f"Received Time       : {self.last_packet_time}")
        print(f"From i.MX93         : {sender[0]}:{sender[1]}")

        # UDP streamer-level metadata
        if "sequence_number" in packet:
            print(f"Sequence Number     : {packet.get('sequence_number')}")

        if "sent_timestamp" in packet:
            print(f"Sent Timestamp      : {packet.get('sent_timestamp')}")

        # Gateway payload metadata
        print("----------------------------------------------------")
        print(f"Payload Type        : {payload.get('type')}")
        print(f"Gateway ID          : {payload.get('gateway_id')}")
        print(f"Asset ID            : {payload.get('asset_id')}")
        print(f"Gateway Timestamp   : {payload.get('timestamp')}")
        print(f"Status              : {payload.get('status')}")

        if payload.get("error"):
            print(f"Error               : {payload.get('error')}")

        print("----------------------------------------------------")
        print("Chiller Telemetry")
        print("----------------------------------------------------")

        if not telemetry_data:
            print("No telemetry data found in packet")
        else:
            for key, value in telemetry_data.items():
                print(f"{key:28}: {value}")

        print("====================================================")


# -------------------------------------------------
# CLI Arguments
# -------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PC UDP Listener for EMS Gateway Telemetry"
    )

    parser.add_argument(
        "--ip",
        default="0.0.0.0",
        help="IP address to listen on. Default: 0.0.0.0",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=5005,
        help="UDP port to listen on. Default: 5005",
    )

    return parser.parse_args()


# -------------------------------------------------
# Main
# -------------------------------------------------

def main() -> None:
    args = parse_args()

    listener = PCUDPListener(
        listen_ip=args.ip,
        listen_port=args.port,
    )

    try:
        listener.start()

    except KeyboardInterrupt:
        print("\n[PC UDP] Ctrl+C received")

    except Exception as e:
        print(f"\n[PC UDP] Fatal error: {e}")

    finally:
        listener.stop()


if __name__ == "__main__":
    main()