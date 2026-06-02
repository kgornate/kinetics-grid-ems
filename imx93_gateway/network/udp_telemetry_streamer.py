"""
UDP Telemetry Streamer for i.MX93 EMS Gateway.

Role:
- Sends latest EMS telemetry from i.MX93 Gateway to PC Dashboard.
- Asset-agnostic: Chiller, PCS, and BMS data are prepared by main.py callback.
- Uses UDP socket communication.
"""

import json
import socket
import threading
import time
from datetime import datetime
from typing import Callable, Dict, Any, Optional


class UDPTelemetryStreamer:
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

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _create_socket(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def _close_socket(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def start(self) -> None:
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
            f"destination={self.pc_ip}:{self.pc_port}, interval={self.interval_sec}s"
        )

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._close_socket()
        print("[UDP] Telemetry streamer stopped")

    def is_running(self) -> bool:
        return self._running

    def _stream_loop(self) -> None:
        while self._running:
            try:
                self.send_once()
            except Exception as e:
                self.last_error = str(e)
                print(f"[UDP] Telemetry send error: {e}")
            time.sleep(self.interval_sec)

    def send_once(self) -> bool:
        if self.sock is None:
            raise RuntimeError("UDP socket is not created. Call start() first.")

        telemetry_packet = self.get_telemetry_callback()
        if not isinstance(telemetry_packet, dict):
            raise ValueError("Telemetry callback must return a dictionary")

        self.sequence_number += 1
        packet = {
            "streamer": self.streamer_name,
            "sequence_number": self.sequence_number,
            "sent_timestamp": self._now(),
            "payload": telemetry_packet,
        }

        message = json.dumps(packet, default=str)
        self.sock.sendto(message.encode("utf-8"), (self.pc_ip, self.pc_port))

        self.last_sent_time = self._now()
        self.last_error = None
        print(f"[UDP] Sent telemetry packet #{self.sequence_number} to {self.pc_ip}:{self.pc_port}")
        return True

    def get_status(self) -> Dict[str, Any]:
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


def _mock_telemetry_packet() -> Dict[str, Any]:
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
            "bms": {
                "asset_id": "bms_1",
                "communication_status": "online",
                "soc_percent": 72.0,
                "soh_percent": 98.0,
                "rack_voltage_v": 768.5,
                "rack_current_a": -35.2,
                "power_kw": -27.051,
                "alarm_count": 0,
                "active_alarms": [],
            },
        },
    }


if __name__ == "__main__":
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
