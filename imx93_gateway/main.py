"""
Main Application Entry Point for i.MX93 EMS Gateway.

Role of this file:
- Starts the complete EMS Gateway backend.
- In REAL mode:
    - Connects to chiller over Modbus RTU.
    - Polls chiller data.
    - Sends UDP telemetry to PC.
    - Receives TCP commands from PC.

- In MOCK mode:
    - Does not use Modbus.
    - Does not need chiller hardware.
    - Sends dummy telemetry to PC.
    - Receives TCP commands and returns mock responses.

Run real mode on i.MX93:

    python3 imx93_gateway/main.py --pc-ip <PC_IP>

Run mock mode on i.MX93:

    python3 imx93_gateway/main.py --mock --pc-ip <PC_IP>

Run mock mode on PC:

    python imx93_gateway\\main.py --mock --pc-ip 127.0.0.1
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
# Config Import
# -------------------------------------------------

try:
    import config as cfg
except ImportError:
    cfg = None


# -------------------------------------------------
# Network imports
# -------------------------------------------------
# These do not depend on pymodbus.
# Safe for both mock mode and real mode.
# -------------------------------------------------

from network.udp_telemetry_streamer import UDPTelemetryStreamer
from network.tcp_command_server import TCPCommandServer


# -------------------------------------------------
# Config Helper
# -------------------------------------------------

def get_config_value(name: str, default: Any) -> Any:
    """
    Read value from config.py.
    If config.py or value is missing, return default.
    """

    if cfg is None:
        return default

    return getattr(cfg, name, default)


# -------------------------------------------------
# Mock Gateway Service
# -------------------------------------------------
# This service is used when --mock is enabled.
# It does not use Modbus and does not require chiller hardware.
# -------------------------------------------------

class MockGatewayService:
    """
    Mock service for testing TCP/UDP communication without Modbus hardware.

    It provides the same main APIs as ChillerGatewayService:
        start_polling()
        stop_polling()
        get_telemetry_packet()
        execute_command()

    This allows the Flutter dashboard and PC TCP/UDP tools to be tested
    before going to the actual chiller site.
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
            "control_mode": 2,
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
        Return dummy telemetry packet for UDP streaming.
        """

        self.sequence += 1

        # Small changing values to confirm that live UDP telemetry is updating.
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

        This mimics the real ChillerGatewayService response shapes so the
        Flutter dashboard can display READ_MODE, READ_TEMP, READ_ONOFF,
        and READ_SETTINGS properly.

        No real Modbus command is executed.
        """

        request_id = command_packet.get("request_id")
        command = str(command_packet.get("command", "")).strip().upper()
        value = command_packet.get("value")

        def response(message: str, data: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "type": "response",
                "request_id": request_id,
                "timestamp": self._now(),
                "status": "ok",
                "command": command,
                "message": message,
                "data": data,
            }

        def error_response(message: str) -> Dict[str, Any]:
            return {
                "type": "response",
                "request_id": request_id,
                "timestamp": self._now(),
                "status": "error",
                "command": command,
                "message": message,
                "data": {},
            }

        try:
            set_temp = float(self.mock_state.get("set_temperature", 25.0))
            set_temp_raw = int(set_temp * 10)

            water_pump_running = self.mock_state.get("water_pump") == "RUNNING"
            onoff_raw = 1 if water_pump_running else 0
            onoff_status = "ON" if onoff_raw == 1 else "OFF"

            control_mode_raw = int(self.mock_state.get("control_mode", 2))

            read_mode_map = {
                1: "Water pump circulation mode",
                2: "Refrigeration / Cooling mode",
                3: "Heating mode",
                4: "System automatic control mode",
            }

            write_to_readback_mode = {
                0: 4,
                1: 2,
                2: 3,
                3: 1,
            }

            write_mode_name = {
                0: "System automatic control mode",
                1: "Refrigeration / Cooling mode",
                2: "Heating mode",
                3: "Water pump circulation mode",
            }

            # -------------------------------------------------
            # Read Commands
            # -------------------------------------------------

            if command == "READ_ALL":
                return response(
                    message="Mock telemetry read successfully",
                    data=dict(self.mock_state),
                )

            if command == "READ_TEMP":
                return response(
                    message="Mock set temperature read successfully",
                    data={
                        "register": 205,
                        "raw_value": set_temp_raw,
                        "temperature_celsius": set_temp,
                    },
                )

            if command == "READ_ONOFF":
                return response(
                    message="Mock ON/OFF status read successfully",
                    data={
                        "register": 201,
                        "raw_value": onoff_raw,
                        "status": onoff_status,
                    },
                )

            if command == "READ_MODE":
                return response(
                    message="Mock control mode read successfully",
                    data={
                        "register": 200,
                        "raw_value": control_mode_raw,
                        "mode": read_mode_map.get(control_mode_raw, "Unknown mode"),
                    },
                )

            if command == "READ_SETTINGS":
                return response(
                    message="Mock setting parameters read successfully",
                    data={
                        "raw_registers_200_to_208": [
                            control_mode_raw,
                            onoff_raw,
                            0,
                            0,
                            0,
                            set_temp_raw,
                            0,
                            0,
                            0,
                        ],
                        "control_mode": {
                            "register": 200,
                            "raw_value": control_mode_raw,
                            "mode": read_mode_map.get(control_mode_raw, "Unknown mode"),
                        },
                        "on_off_enable": {
                            "register": 201,
                            "raw_value": onoff_raw,
                            "status": onoff_status,
                        },
                        "reserved_202": 0,
                        "reserved_203": 0,
                        "reserved_204": 0,
                        "set_temperature": {
                            "register": 205,
                            "raw_value": set_temp_raw,
                            "temperature_celsius": set_temp,
                        },
                        "reserved_206": 0,
                        "reserved_207": 0,
                        "reserved_208": 0,
                    },
                )

            # -------------------------------------------------
            # Write / Control Commands
            # -------------------------------------------------

            if command == "SET_TEMP":
                if value is None:
                    return error_response("SET_TEMP requires value")

                new_temp = float(value)
                new_temp_raw = int(new_temp * 10)

                self.mock_state["set_temperature"] = new_temp

                return response(
                    message="Mock set temperature command executed",
                    data={
                        "status": "ok",
                        "command": "SET_TEMP",
                        "register": 205,
                        "temperature_celsius": new_temp,
                        "written_value": new_temp_raw,
                        "message": "Mock temperature write command successful",
                        "readback": {
                            "register": 205,
                            "raw_value": new_temp_raw,
                            "temperature_celsius": new_temp,
                        },
                        "verified": True,
                    },
                )

            if command == "SET_MODE":
                if value is None:
                    return error_response("SET_MODE requires value")

                write_value = int(value)
                expected_readback = write_to_readback_mode.get(write_value, write_value)
                requested_mode = write_mode_name.get(write_value, "Unknown mode")

                self.mock_state["control_mode"] = expected_readback

                return response(
                    message="Mock set mode command executed",
                    data={
                        "status": "ok",
                        "command": "SET_MODE",
                        "register": 200,
                        "written_value": write_value,
                        "requested_mode": requested_mode,
                        "message": "Mock mode write command successful",
                        "expected_readback_value": expected_readback,
                        "readback": {
                            "register": 200,
                            "raw_value": expected_readback,
                            "mode": read_mode_map.get(expected_readback, "Unknown mode"),
                        },
                        "verified": True,
                    },
                )

            if command == "CHILLER_ON":
                self.mock_state["water_pump"] = "RUNNING"

                return response(
                    message="Mock CHILLER_ON command executed",
                    data={
                        "status": "ok",
                        "command": "CHILLER_ON",
                        "register": 201,
                        "written_value": 1,
                        "message": "Mock chiller ON command successful",
                        "readback": {
                            "register": 201,
                            "raw_value": 1,
                            "status": "ON",
                        },
                        "verified": True,
                    },
                )

            if command == "CHILLER_OFF":
                self.mock_state["water_pump"] = "STOPPED"

                return response(
                    message="Mock CHILLER_OFF command executed",
                    data={
                        "status": "ok",
                        "command": "CHILLER_OFF",
                        "register": 201,
                        "written_value": 0,
                        "message": "Mock chiller OFF command successful",
                        "readback": {
                            "register": 201,
                            "raw_value": 0,
                            "status": "OFF",
                        },
                        "verified": True,
                    },
                )

            return error_response(f"Unsupported mock command: {command}")

        except Exception as e:
            return error_response(str(e))


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

        self.driver: Optional[Any] = None
        self.service: Optional[Any] = None
        self.udp_streamer: Optional[UDPTelemetryStreamer] = None
        self.tcp_server: Optional[TCPCommandServer] = None

        self.running = False

        self.gateway_id = get_config_value("GATEWAY_ID", "imx93_gateway_1")
        self.asset_id = get_config_value("ASSET_ID", "chiller_1")

        self.modbus_port = args.serial_port or get_config_value(
            "MODBUS_PORT",
            "/dev/ttyUSB0",
        )
        self.modbus_baudrate = get_config_value("MODBUS_BAUDRATE", 9600)
        self.modbus_bytesize = get_config_value("MODBUS_BYTESIZE", 8)
        self.modbus_parity = get_config_value("MODBUS_PARITY", "N")
        self.modbus_stopbits = get_config_value("MODBUS_STOPBITS", 1)
        self.modbus_timeout = get_config_value("MODBUS_TIMEOUT_SEC", 2.0)
        self.chiller_slave_id = args.slave_id or get_config_value(
            "CHILLER_SLAVE_ID",
            1,
        )

        self.tcp_host = get_config_value("TCP_COMMAND_HOST", "0.0.0.0")
        self.tcp_port = args.tcp_port or get_config_value(
            "TCP_COMMAND_PORT",
            6000,
        )

        self.pc_telemetry_ip = args.pc_ip or get_config_value(
            "PC_TELEMETRY_IP",
            "192.168.10.1",
        )
        self.udp_telemetry_port = args.udp_port or get_config_value(
            "UDP_TELEMETRY_PORT",
            5005,
        )

        self.poll_interval_sec = args.poll_interval or get_config_value(
            "CHILLER_POLL_INTERVAL_SEC",
            1.0,
        )
        self.udp_interval_sec = args.udp_interval or get_config_value(
            "UDP_TELEMETRY_INTERVAL_SEC",
            1.0,
        )

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

    def _start_real_chiller_service(self) -> None:
        """
        Start real Modbus chiller service.

        Imports are done here intentionally so mock mode can run even if
        pymodbus is not installed on the PC.
        """

        print("[MAIN] Starting real chiller Modbus service...")

        try:
            from drivers.chiller_modbus_driver import ChillerModbusDriver
            from services.chiller_gateway_service import ChillerGatewayService
        except ImportError as e:
            raise RuntimeError(
                "Failed to import real Modbus gateway modules. "
                "Make sure pymodbus and pyserial are installed. "
                "Install using: pip3 install pymodbus pyserial"
            ) from e

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
                f"Check USB-RS485 adapter, wiring, serial port, and slave ID."
            )

        self.service = ChillerGatewayService(
            driver=self.driver,
            gateway_id=self.gateway_id,
            asset_id=self.asset_id,
            poll_interval_sec=self.poll_interval_sec,
        )

        self.service.start_polling()

    def _start_udp_streamer(self) -> None:
        """
        Start UDP telemetry streamer.
        """

        if self.service is None:
            raise RuntimeError("Service not initialized before starting UDP streamer")

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

        if self.service is None:
            raise RuntimeError("Service not initialized before starting TCP server")

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
    # Banner
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