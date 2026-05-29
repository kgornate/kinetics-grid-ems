"""
UDP Telemetry Streamer for i.MX93 EMS Gateway.

Role of this file:
- Sends latest EMS telemetry from i.MX93 Gateway to PC Dashboard.
- Uses UDP socket communication.
- Gets latest telemetry packet from the EMS application/service callback.
- Sends telemetry periodically, for example every 1 second.

Direction:
    i.MX93 Gateway  --->  PC Dashboard

This file does not directly communicate with Modbus.
It only sends already-prepared telemetry packets over Ethernet using UDP.

Final flow:
    ChillerModbusDriver / PcsGatewayService
            ↓
    EMS Gateway Application telemetry callback
            ↓
    UDPTelemetryStreamer
            ↓
    Ethernet UDP
            ↓
    PC Dashboard / Flutter GUI
"""

import json
import socket
import threading
import time
from datetime import datetime
from typing import Callable, Dict, Any, Optional


class UDPTelemetryStreamer:
    """
    UDP telemetry streamer.

    This class periodically calls a callback function to get the latest
    telemetry packet and sends it to the PC dashboard using UDP.

    Example callback:
        app.get_udp_telemetry_packet

    Example usage:
        streamer = UDPTelemetryStreamer(
            pc_ip="192.168.10.1",
            pc_port=5005,
            get_telemetry_callback=app.get_udp_telemetry_packet,
            interval_sec=1.0
        )

        streamer.start()
    """

    def __init__(
        self,
        pc_ip: str,
        pc_port: int,
        get_telemetry_callback: Callable[[], Dict[str, Any]],
        interval_sec: float = 1.0,
        streamer_name: str = "ems_udp_telemetry_streamer",
    ):
        self.pc_ip = pc_ip
        self.pc_port = int(pc_port)
        self.get_telemetry_callback = get_telemetry_callback
        self.interval_sec = float(interval_sec)
        self.streamer_name = streamer_name

        self.sock: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self.sequence_number = 0
        self.last_sent_time: Optional[str] = None
        self.last_error: Optional[str] = None

    # -------------------------------------------------
    # Utility
    # -------------------------------------------------

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _create_socket(self) -> None:
        """
        Create UDP socket.
        """

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Allow quick restart of the application.
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def _close_socket(self) -> None:
        """
        Close UDP socket.
        """

        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass

            self.sock = None

    # -------------------------------------------------
    # Start / Stop APIs
    # -------------------------------------------------

    def start(self) -> None:
        """
        Start UDP telemetry streaming in a background thread.
        """

        if self._running:
            print("[UDP] Telemetry streamer already running")
            return

        self._create_socket()

        self._running = True

        self._thread = threading.Thread(
            target=self._stream_loop,
            name="UDPTelemetryStreamerThread",
            daemon=True,
        )

        self._thread.start()

        print(
            f"[UDP] Telemetry streamer started | "
            f"destination={self.pc_ip}:{self.pc_port}, "
            f"interval={self.interval_sec}s"
        )

    def stop(self) -> None:
        """
        Stop UDP telemetry streaming.
        """

        if not self._running:
            return

        self._running = False

        if self._thread is not None:
            self._thread.join(timeout=2)

        self._close_socket()

        print("[UDP] Telemetry streamer stopped")

    def is_running(self) -> bool:
        """
        Return streamer running status.
        """

        return self._running

    # -------------------------------------------------
    # Main Streaming Loop
    # -------------------------------------------------

    def _stream_loop(self) -> None:
        """
        Internal loop that sends telemetry at fixed interval.
        """

        while self._running:
            try:
                self.send_once()

            except Exception as e:
                self.last_error = str(e)
                print(f"[UDP] Telemetry send error: {e}")

            time.sleep(self.interval_sec)

    def send_once(self) -> bool:
        """
        Send one telemetry packet.

        This is useful for:
        - Periodic streaming
        - Manual testing
        - Future debug commands
        """

        if self.sock is None:
            raise RuntimeError("UDP socket is not created. Call start() first.")

        telemetry_packet = self.get_telemetry_callback()

        if not isinstance(telemetry_packet, dict):
            raise ValueError("Telemetry callback must return a dictionary")

        self.sequence_number += 1

        # Add UDP-level metadata without disturbing service-level data.
        packet = {
            "streamer": self.streamer_name,
            "sequence_number": self.sequence_number,
            "sent_timestamp": self._now(),
            "payload": telemetry_packet,
        }

        message = json.dumps(packet, default=str)
        encoded_message = message.encode("utf-8")

        self.sock.sendto(encoded_message, (self.pc_ip, self.pc_port))

        self.last_sent_time = self._now()
        self.last_error = None

        print(
            f"[UDP] Sent telemetry packet #{self.sequence_number} "
            f"to {self.pc_ip}:{self.pc_port}"
        )

        return True

    # -------------------------------------------------
    # Status API
    # -------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """
        Return current streamer status.
        """

        return {
            "streamer_name": self.streamer_name,
            "running": self._running,
            "pc_ip": self.pc_ip,
            "pc_port": self.pc_port,
            "interval_sec": self.interval_sec,
            "sequence_number": self.sequence_number,
            "last_sent_time": self.last_sent_time,
            "last_error": self.last_error,
        }


# -------------------------------------------------
# Standalone Mock Test
# -------------------------------------------------
# This does not require chiller or PCS hardware.
# It only sends dummy telemetry to PC UDP listener.
#
# Later test command:
#   python3 network/udp_telemetry_streamer.py
#
# Make sure PC UDP listener is running on UDP port 5005.
# -------------------------------------------------

def _mock_telemetry_packet() -> Dict[str, Any]:
    """
    Dummy telemetry packet for testing UDP communication only.
    This does not use Modbus or hardware.
    """

    return {
        "type": "telemetry",
        "gateway_id": "imx93_gateway_1",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": "ok",
        "mode": "mock",
        "assets": {
            "chiller": {
                "asset_id": "chiller_1",
                "status": "ok",
                "data": {
                    "water_pump": "RUNNING",
                    "outlet_water_temp": 38.4,
                    "return_water_temp": 38.1,
                    "communication_status": "mock",
                },
            },
            "pcs": {
                "asset_id": "pcs_1",
                "comm_status": "online",
                "active_power_kw": 20.0,
                "dc_power_kw": 20.0,
                "frequency_hz": 50.0,
                "operating_status": "running_grid_connected",
            },
        },
    }


if __name__ == "__main__":
    """
    Standalone mock execution.

    This is only for UDP communication testing.
    In final gateway, this class will be started from main.py.
    """

    PC_IP = "192.168.10.1"
    PC_PORT = 5005

    streamer = UDPTelemetryStreamer(
        pc_ip=PC_IP,
        pc_port=PC_PORT,
        get_telemetry_callback=_mock_telemetry_packet,
        interval_sec=1.0,
    )

    try:
        streamer.start()

        print("[UDP TEST] Press Ctrl+C to stop")
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[UDP TEST] Stopping...")

    finally:
        streamer.stop()