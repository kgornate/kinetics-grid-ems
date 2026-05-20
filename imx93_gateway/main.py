"""
Main Application Entry Point for i.MX93 EMS Gateway.

Role of this file:
- Starts the complete EMS Gateway backend on FRDM i.MX93.
- Connects to chiller over Modbus RTU.
- Starts periodic chiller polling.
- Starts UDP telemetry streaming to PC dashboard.
- Starts TCP command server for PC dashboard control commands.

Final runtime flow:

    Chiller / Liquid Cooling System
            ⇅ Modbus RTU / RS485
    ChillerModbusDriver
            ⇅
    ChillerGatewayService
            ⇅
    TCPCommandServer + UDPTelemetryStreamer
            ⇅ Ethernet TCP/UDP
    PC Dashboard / Flutter GUI

Run on i.MX93:

    python3 imx93_gateway/main.py

For network-only mock testing without chiller hardware:

    python3 imx93_gateway/main.py --mock --pc-ip <PC_IP>
"""

import argparse
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


# -------------------------------------------------
# Import support
# -------------------------------------------------

CURRENT_FILE = Path(__file__).resolve()
IMX93_GATEWAY_DIR = CURRENT_FILE.parent

if str(IMX93_GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(IMX93_GATEWAY_DIR))


# -------------------------------------------------
# Project imports
# -------------------------------------------------

import config as cfg

from drivers.chiller_modbus_driver import ChillerModbusDriver
from services.chiller_gateway_service import ChillerGatewayService
from network.udp_telemetry_streamer import UDPTelemetryStreamer
from network.tcp_command_server import TCPCommandServer


# -------------------------------------------------
# Default Config Getter
# -------------------------------------------------

def get_config_value(name: str, default: Any) -> Any:
    """
    Read value from config.py.
    If not available, use default.
    """

    return getattr(cfg, name, default)


# -------------------------------------------------
# Mock Gateway Service
# -------------------------------------------------
# This allows Ethernet TCP/UDP testing without actual chiller hardware.
# Useful before going to the liquid cooling system site.
# -------------------------------------------------

class MockGatewayService:
    """
    Mock service for testing TCP/UDP communication without Modbus hardware.

    It provides the same APIs as ChillerGatewayService:
        get_telemetry_packet()
        execute_command()
        start_polling()
        stop_polling()
    """

    def __init__(
        self,
        gateway_id: str = "imx93_gateway_1",
        asset_id: str = "chiller_1",
    ):
        self.gateway_id = gateway_id
        self.asset_id = asset_id
        self.sequence = 0
        self.running = False

        self.mock_state = {
            "water_pump": "RUNNING",
            "compressor1": "STOPPED",
            "compressor2": "STOPPED",
            "electric_heater": "STOPPED",
            "condensate_fan": "STOPPED",
            "outlet_water_temp": 38.4,
            "return_water_temp": 38.1,
            "outlet_water_pressure": 0.27,
            "return_water_pressure": 0.07,
            "ambient_temp": 37.4,
            "makeup_pump": "ON",
            "fault_code": 0,
            "control_mode": "mock",
            "set_temperature": 25.0,
            "communication_status": "mock",
        }

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def start_polling(self) -> None:
        self.running = True
        print("[MOCK SERVICE] Mock polling started")

    def stop_polling(self) -> None:
        self.running = False
        print("[MOCK SERVICE] Mock polling stopped")

    def get_telemetry_packet(self) -> Dict[str, Any]:
        """
        Return dummy telemetry packet.
        """

        self.sequence += 1

        # Small changing value to confirm live UDP streaming.
        self.mock_state["outlet_water_temp"] = 38.4 + (self.sequence % 5) * 0.1
        self.mock_state["return_water_temp"] = 38.1 + (self.sequence % 5) * 0.1

        return {
            "type": "telemetry",
            "gateway_id": self.gateway_id,
            "asset_id": self.asset_id,
            "timestamp": self._now(),
            "status": "ok",
            "mode": "mock",
            "data": dict(self.mock_state),
        }

    def execute_command(self, command_packet: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mock command execution.
        Does not talk to real chiller.
        """

        request_id = command_packet.get("request_id")
        command = str(command_packet.get("command", "")).strip().upper()
        value = command_packet.get("value")

        if command == "SET_TEMP":
            self.mock_state["set_temperature"] = float(value)

        elif command == "SET_MODE":
            self.mock_state["control_mode"] = value

        elif command == "CHILLER_ON":
            self.mock_state["water_pump"] = "RUNNING"

        elif command == "CHILLER_OFF":
            self.mock_state["water_pump"] = "STOPPED"

        return {
            "type": "response",
            "request_id": request_id,
            "timestamp": self._now(),
            "status": "ok",
            "command": command,
            "message": "Mock command executed successfully. No Modbus command sent.",
            "data": {
                "received_command": command,
                "received_value": value,
                "mock_state": dict(self.mock_state),
            },
        }


# -------------------------------------------------
# Gateway Application
# -------------------------------------------------

class EMSGatewayApplication:
    """
    Main EMS Gateway Application.

    This class owns:
    - Chiller Modbus driver
    - Chiller gateway service
    - UDP telemetry streamer
    - TCP command server
    """

    def __init__(self, args: argparse.Namespace):
        self.args = args

        self.driver: Optional[ChillerModbusDriver] = None
        self.service: Optional[Any] = None
        self.udp_streamer: Optional[UDPTelemetryStreamer] = None
        self.tcp_server: Optional[TCPCommandServer] = None

        self.running = False

        self.gateway_id = get_config_value("GATEWAY_ID", "imx93_gateway_1")
        self.asset_id = get_config_value("ASSET_ID", "chiller_1")

        self.modbus_port = args.serial_port or get_config_value("MODBUS_PORT", "/dev/ttyUSB0")
        self.modbus_baudrate = get_config_value("MODBUS_BAUDRATE", 9600)
        self.modbus_bytesize = get_config_value("MODBUS_BYTESIZE", 8)
        self.modbus_parity = get_config_value("MODBUS_PARITY", "N")
        self.modbus_stopbits = get_config_value("MODBUS_STOPBITS", 1)
        self.modbus_timeout = get_config_value("MODBUS_TIMEOUT_SEC", 2.0)
        self.chiller_slave_id = args.slave_id or get_config_value("CHILLER_SLAVE_ID", 1)

        self.tcp_host = get_config_value("TCP_COMMAND_HOST", "0.0.0.0")
        self.tcp_port = args.tcp_port or get_config_value("TCP_COMMAND_PORT", 6000)

        self.pc_telemetry_ip = args.pc_ip or get_config_value("PC_TELEMETRY_IP", "192.168.1.10")
        self.udp_telemetry_port = args.udp_port or get_config_value("UDP_TELEMETRY_PORT", 5005)

        self.poll_interval_sec = args.poll_interval or get_config_value("CHILLER_POLL_INTERVAL_SEC", 1.0)
        self.udp_interval_sec = args.udp_interval or get_config_value("UDP_TELEMETRY_INTERVAL_SEC", 1.0)

    # -------------------------------------------------
    # Startup
    # -------------------------------------------------

    def start(self) -> None:
        """
        Start complete gateway application.
        """

        self.print_startup_banner()

        if self.args.mock:
            self._start_mock_service()
        else:
            self._start_real_chiller_service()

        if not self.args.no_udp:
            self._start_udp_streamer()

        if not self.args.no_tcp:
            self._start_tcp_server()

        self.running = True

        print("\n[MAIN] EMS Gateway started successfully")
        print("[MAIN] Press Ctrl+C to stop\n")

    def _start_real_chiller_service(self) -> None:
        """
        Start real Modbus chiller service.
        """

        print("[MAIN] Starting real chiller Modbus service...")

        self.driver = ChillerModbusDriver(
            port=self.modbus_port,
            slave_id=self.chiller_slave_id,
            baudrate=self.modbus_baudrate,
            bytesize=self.modbus_bytesize,
            parity=self.modbus_parity,
            stopbits=self.modbus_stopbits,
            timeout=self.modbus_timeout,
        )

        connected = self.driver.connect()

        if not connected:
            raise RuntimeError(
                f"Failed to connect to chiller on {self.modbus_port}. "
                f"Check USB-RS485, wiring, port, and slave ID."
            )

        self.service = ChillerGatewayService(
            driver=self.driver,
            gateway_id=self.gateway_id,
            asset_id=self.asset_id,
            poll_interval_sec=self.poll_interval_sec,
        )

        self.service.start_polling()

    def _start_mock_service(self) -> None:
        """
        Start mock service for TCP/UDP testing without chiller.
        """

        print("[MAIN] Starting MOCK gateway service. No Modbus hardware will be used.")

        self.service = MockGatewayService(
            gateway_id=self.gateway_id,
            asset_id=self.asset_id,
        )

        self.service.start_polling()

    def _start_udp_streamer(self) -> None:
        """
        Start UDP telemetry streamer.
        """

        print("[MAIN] Starting UDP telemetry streamer...")

        self.udp_streamer = UDPTelemetryStreamer(
            pc_ip=self.pc_telemetry_ip,
            pc_port=self.udp_telemetry_port,
            get_telemetry_callback=self.service.get_telemetry_packet,
            interval_sec=self.udp_interval_sec,
        )

        self.udp_streamer.start()

    def _start_tcp_server(self) -> None:
        """
        Start TCP command server.
        """

        print("[MAIN] Starting TCP command server...")

        self.tcp_server = TCPCommandServer(
            host=self.tcp_host,
            port=self.tcp_port,
            command_handler=self.service.execute_command,
        )

        self.tcp_server.start()

    # -------------------------------------------------
    # Runtime Loop
    # -------------------------------------------------

    def run_forever(self) -> None:
        """
        Keep main application alive.
        """

        while self.running:
            time.sleep(1)

    # -------------------------------------------------
    # Shutdown
    # -------------------------------------------------

    def stop(self) -> None:
        """
        Stop complete gateway application safely.
        """

        print("\n[MAIN] Stopping EMS Gateway...")

        self.running = False

        if self.tcp_server is not None:
            try:
                self.tcp_server.stop()
            except Exception as e:
                print(f"[MAIN] Error while stopping TCP server: {e}")

        if self.udp_streamer is not None:
            try:
                self.udp_streamer.stop()
            except Exception as e:
                print(f"[MAIN] Error while stopping UDP streamer: {e}")

        if self.service is not None:
            try:
                self.service.stop_polling()
            except Exception as e:
                print(f"[MAIN] Error while stopping service: {e}")

        if self.driver is not None:
            try:
                self.driver.close()
            except Exception as e:
                print(f"[MAIN] Error while closing Modbus driver: {e}")

        print("[MAIN] EMS Gateway stopped")

    # -------------------------------------------------
    # Status / Logging
    # -------------------------------------------------

    def print_startup_banner(self) -> None:
        """
        Print startup configuration.
        """

        print("\n====================================================")
        print("          i.MX93 EMS Gateway Backend")
        print("====================================================")
        print(f"Gateway ID              : {self.gateway_id}")
        print(f"Asset ID                : {self.asset_id}")
        print(f"Mode                    : {'MOCK' if self.args.mock else 'REAL CHILLER'}")
        print("")
        print("Modbus RTU Configuration")
        print("----------------------------------------------------")
        print(f"Serial Port             : {self.modbus_port}")
        print(f"Slave ID                : {self.chiller_slave_id}")
        print(f"Baudrate                : {self.modbus_baudrate}")
        print(f"Serial Format           : {self.modbus_bytesize}{self.modbus_parity}{self.modbus_stopbits}")
        print(f"Timeout                 : {self.modbus_timeout} sec")
        print(f"Polling Interval        : {self.poll_interval_sec} sec")
        print("")
        print("Ethernet / Network Configuration")
        print("----------------------------------------------------")
        print(f"TCP Command Host        : {self.tcp_host}")
        print(f"TCP Command Port        : {self.tcp_port}")
        print(f"UDP Telemetry PC IP     : {self.pc_telemetry_ip}")
        print(f"UDP Telemetry Port      : {self.udp_telemetry_port}")
        print(f"UDP Telemetry Interval  : {self.udp_interval_sec} sec")
        print(f"UDP Disabled            : {self.args.no_udp}")
        print(f"TCP Disabled            : {self.args.no_tcp}")
        print("====================================================\n")


# -------------------------------------------------
# CLI Arguments
# -------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="i.MX93 EMS Gateway Backend"
    )

    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run gateway in mock mode without Modbus/chiller hardware",
    )

    parser.add_argument(
        "--serial-port",
        default=None,
        help="Override Modbus serial port, example: /dev/ttyUSB1",
    )

    parser.add_argument(
        "--slave-id",
        type=int,
        default=None,
        help="Override chiller Modbus slave ID",
    )

    parser.add_argument(
        "--pc-ip",
        default=None,
        help="Override PC telemetry destination IP address",
    )

    parser.add_argument(
        "--udp-port",
        type=int,
        default=None,
        help="Override UDP telemetry destination port",
    )

    parser.add_argument(
        "--tcp-port",
        type=int,
        default=None,
        help="Override TCP command server port",
    )

    parser.add_argument(
        "--poll-interval",
        type=float,
        default=None,
        help="Override chiller Modbus polling interval in seconds",
    )

    parser.add_argument(
        "--udp-interval",
        type=float,
        default=None,
        help="Override UDP telemetry interval in seconds",
    )

    parser.add_argument(
        "--no-udp",
        action="store_true",
        help="Disable UDP telemetry streamer",
    )

    parser.add_argument(
        "--no-tcp",
        action="store_true",
        help="Disable TCP command server",
    )

    return parser.parse_args()


# -------------------------------------------------
# Main
# -------------------------------------------------

def main() -> None:
    args = parse_args()

    app = EMSGatewayApplication(args)

    def handle_shutdown(signum, frame):
        app.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        app.start()
        app.run_forever()

    except KeyboardInterrupt:
        app.stop()

    except Exception as e:
        print(f"[MAIN] Fatal error: {e}")
        app.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()