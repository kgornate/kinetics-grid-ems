"""
Main Application Entry Point for i.MX93 EMS Gateway.

Role of this file:
- Starts the complete EMS Gateway backend.

In REAL mode:
    - Optionally connects to chiller over Modbus RTU.
    - Optionally connects to PCS/Inverter over Modbus TCP.
    - Polls chiller data.
    - Polls PCS data.
    - Sends UDP telemetry to PC.
    - Receives TCP commands from PC.
    - Exposes eMMC/SD logs over HTTP API.

In MOCK mode:
    - Does not use Modbus.
    - Does not need chiller or PCS hardware.
    - Sends dummy chiller telemetry to PC.
    - Receives TCP commands and returns mock responses.
    - Can still expose existing logs over HTTP API.

Current MVP network:
    PC / ModSim / Flutter = 192.168.10.1
    i.MX93 EMS Gateway    = 192.168.10.2

Run real mode on i.MX93:
    python3 main.py --pc-ip 192.168.10.1

Run PCS-only real mode on i.MX93:
    python3 main.py --no-chiller --pc-ip 192.168.10.1

Run mock mode on i.MX93:
    python3 main.py --mock --pc-ip 192.168.10.1

Run mock mode on PC:
    python main.py --mock --pc-ip 127.0.0.1
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

from network.udp_telemetry_streamer import UDPTelemetryStreamer
from network.tcp_command_server import TCPCommandServer
from network.log_http_server import LogHTTPServer
from services.log_query_service import LogQueryService


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

class MockGatewayService:
    """
    Mock service for testing TCP/UDP communication without Modbus hardware.
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
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def start_polling(self) -> None:
        self.running = True
        print("[MOCK SERVICE] Mock polling started")

    def stop_polling(self) -> None:
        self.running = False
        print("[MOCK SERVICE] Mock polling stopped")

    def get_telemetry_packet(self) -> Dict[str, Any]:
        self.sequence += 1

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

        except Exception as error:
            return error_response(str(error))


# -------------------------------------------------
# Gateway Application
# -------------------------------------------------

class EMSGatewayApplication:
    """
    Main EMS Gateway Application.

    This class owns:
    - Chiller Modbus RTU driver/service
    - PCS Modbus TCP service
    - UDP telemetry streamer
    - TCP command server
    - HTTP log API server
    """

    def __init__(self, args: argparse.Namespace):
        self.args = args

        self.chiller_driver: Optional[Any] = None
        self.chiller_service: Optional[Any] = None
        self.mock_service: Optional[MockGatewayService] = None

        self.pcs_service: Optional[Any] = None

        self.udp_streamer: Optional[UDPTelemetryStreamer] = None
        self.tcp_server: Optional[TCPCommandServer] = None
        self.log_query_service: Optional[LogQueryService] = None
        self.log_http_server: Optional[LogHTTPServer] = None

        self.running = False

        self.gateway_id = get_config_value("GATEWAY_ID", "imx93_gateway_1")
        self.asset_id = get_config_value("ASSET_ID", "chiller_1")

        # Chiller configuration
        self.chiller_enabled = bool(get_config_value("CHILLER_ENABLED", True)) and not args.no_chiller

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

        # PCS configuration
        self.pcs_enabled = bool(get_config_value("PCS_ENABLED", False)) and not args.no_pcs
        self.pcs_vendor = args.pcs_vendor or get_config_value("PCS_VENDOR", "njoy")
        self.pcs_asset_id = get_config_value("PCS_ASSET_ID", "pcs_1")
        self.pcs_host = args.pcs_host or get_config_value("PCS_HOST", "192.168.10.1")
        self.pcs_port = args.pcs_port or get_config_value("PCS_PORT", 502)
        self.pcs_unit_id = args.pcs_unit or get_config_value("PCS_UNIT_ID", 1)
        self.pcs_timeout = get_config_value("PCS_TIMEOUT_SEC", 3.0)
        self.pcs_retries = get_config_value("PCS_RETRIES", 2)
        self.pcs_poll_interval_sec = args.pcs_poll_interval or get_config_value(
            "PCS_POLL_INTERVAL_SEC",
            5.0,
        )

        # Network configuration
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

        # Log HTTP configuration
        self.enable_log_http_server = bool(
            get_config_value("ENABLE_LOG_HTTP_SERVER", True)
        )
        self.log_http_host = get_config_value("LOG_HTTP_HOST", "0.0.0.0")
        self.log_http_port = args.log_http_port or get_config_value(
            "LOG_HTTP_PORT",
            7000,
        )
        self.log_base_path = get_config_value(
            "LOG_BASE_PATH",
            "/home/root/ems_logs_test",
        )
        self.log_api_max_rows = get_config_value(
            "LOG_API_MAX_ROWS",
            500,
        )

    # -------------------------------------------------
    # Utility
    # -------------------------------------------------

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def _response(
        self,
        request_id: Optional[Any],
        command: str,
        status: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "type": "response",
            "request_id": request_id,
            "timestamp": self._now(),
            "status": status,
            "command": command,
            "message": message,
            "data": data or {},
        }

    # -------------------------------------------------
    # Startup
    # -------------------------------------------------

    def start(self) -> None:
        self.print_startup_banner()

        if self.args.mock:
            self._start_mock_service()
        else:
            if self.chiller_enabled:
                self._start_real_chiller_service()
            else:
                print("[MAIN] Chiller service disabled")

            if self.pcs_enabled:
                self._start_pcs_service()
            else:
                print("[MAIN] PCS service disabled")

            if not self.chiller_enabled and not self.pcs_enabled:
                raise RuntimeError("Both Chiller and PCS services are disabled. Nothing to run.")

        if not self.args.no_udp:
            self._start_udp_streamer()

        if not self.args.no_tcp:
            self._start_tcp_server()

        if self.enable_log_http_server and not self.args.no_log_http:
            self._start_log_http_server()

        self.running = True

        print("\n[MAIN] EMS Gateway started successfully")
        print("[MAIN] Press Ctrl+C to stop\n")

    def _start_mock_service(self) -> None:
        print("[MAIN] Starting MOCK gateway service. No Modbus hardware will be used.")

        self.mock_service = MockGatewayService(
            gateway_id=self.gateway_id,
            asset_id=self.asset_id,
        )

        self.mock_service.start_polling()

    def _start_real_chiller_service(self) -> None:
        print("[MAIN] Starting real chiller Modbus RTU service...")

        try:
            from drivers.chiller_modbus_driver import ChillerModbusDriver
            from services.chiller_gateway_service import ChillerGatewayService
        except ImportError as error:
            raise RuntimeError(
                "Failed to import real Chiller Modbus gateway modules. "
                "Make sure pymodbus and pyserial are installed. "
                "Install using: pip3 install pymodbus pyserial"
            ) from error

        self.chiller_driver = ChillerModbusDriver(
            port=self.modbus_port,
            slave_id=self.chiller_slave_id,
            baudrate=self.modbus_baudrate,
            bytesize=self.modbus_bytesize,
            parity=self.modbus_parity,
            stopbits=self.modbus_stopbits,
            timeout=self.modbus_timeout,
        )

        connected = self.chiller_driver.connect()

        if not connected:
            raise RuntimeError(
                f"Failed to connect to chiller on {self.modbus_port}. "
                f"Check USB-RS485 adapter, wiring, serial port, and slave ID."
            )

        self.chiller_service = ChillerGatewayService(
            driver=self.chiller_driver,
            gateway_id=self.gateway_id,
            asset_id=self.asset_id,
            poll_interval_sec=self.poll_interval_sec,
        )

        self.chiller_service.start_polling()

    def _start_pcs_service(self) -> None:
        print("[MAIN] Starting PCS/Inverter Modbus TCP service...")

        try:
            from services.pcs_gateway_service import PcsGatewayService
        except ImportError as error:
            raise RuntimeError(
                "Failed to import PCS gateway service. "
                "Make sure drivers/pcs_modbus_tcp_driver.py, "
                "drivers/pcs_profiles/njoy_125kw_profile.py, "
                "models/pcs_state.py, and services/pcs_gateway_service.py exist."
            ) from error

        self.pcs_service = PcsGatewayService(
            asset_id=self.pcs_asset_id,
            vendor=self.pcs_vendor,
            host=self.pcs_host,
            port=self.pcs_port,
            unit_id=self.pcs_unit_id,
            poll_interval_sec=self.pcs_poll_interval_sec,
            timeout=self.pcs_timeout,
            retries=self.pcs_retries,
            gateway_id=self.gateway_id,
            enable_storage_logging=get_config_value("ENABLE_STORAGE_LOGGING", True),
            log_base_path=self.log_base_path,
            log_telemetry_interval_sec=get_config_value(
                "PCS_LOG_TELEMETRY_INTERVAL_SEC",
                get_config_value("LOG_TELEMETRY_INTERVAL_SEC", 5.0),
            ),
        )

        # Start background polling. If ModSim/PCS is temporarily unavailable,
        # the PCS service will mark itself offline and keep retrying on future polls.
        self.pcs_service.start()

        print(
            f"[MAIN] PCS service started | "
            f"vendor={self.pcs_vendor}, host={self.pcs_host}, "
            f"port={self.pcs_port}, unit={self.pcs_unit_id}"
        )

    def _start_udp_streamer(self) -> None:
        print("[MAIN] Starting UDP telemetry streamer...")

        self.udp_streamer = UDPTelemetryStreamer(
            pc_ip=self.pc_telemetry_ip,
            pc_port=self.udp_telemetry_port,
            get_telemetry_callback=self.get_udp_telemetry_packet,
            interval_sec=self.udp_interval_sec,
        )

        self.udp_streamer.start()

    def _start_tcp_server(self) -> None:
        print("[MAIN] Starting TCP command server...")

        self.tcp_server = TCPCommandServer(
            host=self.tcp_host,
            port=self.tcp_port,
            command_handler=self.execute_command,
        )

        self.tcp_server.start()

    def _start_log_http_server(self) -> None:
        print("[MAIN] Starting HTTP log API server...")

        self.log_query_service = LogQueryService(
            base_path=self.log_base_path,
            asset_id=self.asset_id,
            max_rows=self.log_api_max_rows,
        )

        self.log_http_server = LogHTTPServer(
            host=self.log_http_host,
            port=self.log_http_port,
            log_query_service=self.log_query_service,
        )

        self.log_http_server.start()

    # -------------------------------------------------
    # Telemetry Aggregation
    # -------------------------------------------------

    def get_udp_telemetry_packet(self) -> Dict[str, Any]:
        """
        Return one combined EMS telemetry packet.

        Backward compatibility:
        - If chiller telemetry exists, the top-level packet remains close to
          existing chiller telemetry format.
        - PCS telemetry is added under:
              packet["assets"]["pcs"]
              packet["pcs"]
        """

        timestamp = self._now()

        chiller_packet: Optional[Dict[str, Any]] = None
        pcs_packet: Optional[Dict[str, Any]] = None

        if self.args.mock and self.mock_service is not None:
            chiller_packet = self.mock_service.get_telemetry_packet()

        elif self.chiller_service is not None:
            try:
                chiller_packet = self.chiller_service.get_telemetry_packet()
            except Exception as error:
                chiller_packet = {
                    "type": "telemetry",
                    "gateway_id": self.gateway_id,
                    "asset_id": self.asset_id,
                    "timestamp": timestamp,
                    "status": "error",
                    "data": {
                        "communication_status": "offline",
                        "error": str(error),
                    },
                }

        if self.pcs_service is not None:
            try:
                pcs_packet = self.pcs_service.get_latest_state()
            except Exception as error:
                pcs_packet = {
                    "asset_id": self.pcs_asset_id,
                    "vendor": self.pcs_vendor,
                    "comm_status": "offline",
                    "error": str(error),
                }

        # If chiller is running, keep chiller packet as base to avoid breaking
        # existing Flutter code that expects top-level chiller telemetry.
        if chiller_packet is not None:
            packet = dict(chiller_packet)
            packet["gateway_id"] = self.gateway_id
            packet["timestamp"] = packet.get("timestamp", timestamp)
            packet["mode"] = "mock" if self.args.mock else "real"
            packet["assets"] = {
                "chiller": chiller_packet,
                "pcs": pcs_packet,
            }
            packet["pcs"] = pcs_packet
            return packet

        # PCS-only packet
        return {
            "type": "telemetry",
            "gateway_id": self.gateway_id,
            "asset_id": self.pcs_asset_id if pcs_packet else None,
            "timestamp": timestamp,
            "status": "ok" if pcs_packet else "error",
            "mode": "real",
            "data": {
                "message": "PCS-only telemetry packet",
            },
            "assets": {
                "chiller": None,
                "pcs": pcs_packet,
            },
            "pcs": pcs_packet,
        }

    # -------------------------------------------------
    # Command Routing
    # -------------------------------------------------

    def execute_command(self, command_packet: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main EMS command router.

        Routes:
        - PCS_* commands to PCS service.
        - Existing chiller commands to chiller/mock service.
        """

        request_id = command_packet.get("request_id")
        command = str(command_packet.get("command", "")).strip().upper()

        if not command:
            return self._response(
                request_id=request_id,
                command=command,
                status="error",
                message="Missing command",
            )

        # Gateway-level commands
        if command in ["GATEWAY_STATUS", "STATUS"]:
            return self._response(
                request_id=request_id,
                command=command,
                status="ok",
                message="Gateway status read successfully",
                data=self.get_status_packet(),
            )

        if command in ["READ_ALL_ASSETS", "READ_GATEWAY_TELEMETRY"]:
            return self._response(
                request_id=request_id,
                command=command,
                status="ok",
                message="Combined telemetry read successfully",
                data=self.get_udp_telemetry_packet(),
            )

        # PCS command routing
        if (
            command.startswith("PCS_")
            or str(command_packet.get("asset_type", "")).lower() == "pcs"
            or str(command_packet.get("asset_id", "")).lower() == self.pcs_asset_id.lower()
        ):
            return self._execute_pcs_command(command_packet)

        # Chiller / mock command routing
        if self.args.mock and self.mock_service is not None:
            return self.mock_service.execute_command(command_packet)

        if self.chiller_service is not None:
            return self.chiller_service.execute_command(command_packet)

        return self._response(
            request_id=request_id,
            command=command,
            status="error",
            message=f"No service available to handle command: {command}",
        )

    def _execute_pcs_command(self, command_packet: Dict[str, Any]) -> Dict[str, Any]:
        request_id = command_packet.get("request_id")
        command = str(command_packet.get("command", "")).strip().upper()
        value = command_packet.get("value")

        if self.pcs_service is None:
            return self._response(
                request_id=request_id,
                command=command,
                status="error",
                message="PCS service is not running",
            )

        try:
            if command in ["PCS_READ", "READ_PCS", "PCS_STATUS"]:
                return self._response(
                    request_id=request_id,
                    command=command,
                    status="ok",
                    message="PCS state read successfully",
                    data=self.pcs_service.get_latest_state(),
                )

            source = f"flutter_tcp_command:{command_packet.get('client', 'unknown')}"

            if command == "PCS_POWER_ON":
                result = self.pcs_service.power_on(source=source)
                return self._pcs_command_response(request_id, command, result)

            if command == "PCS_POWER_OFF":
                result = self.pcs_service.power_off(source=source)
                return self._pcs_command_response(request_id, command, result)

            if command in ["PCS_STANDBY", "PCS_DEVICE_STANDBY"]:
                result = self.pcs_service.standby(source=source)
                return self._pcs_command_response(request_id, command, result)

            if command == "PCS_SET_ACTIVE_POWER":
                if value is None:
                    value = command_packet.get("kw", command_packet.get("active_power_kw"))

                if value is None:
                    return self._response(
                        request_id=request_id,
                        command=command,
                        status="error",
                        message="PCS_SET_ACTIVE_POWER requires value / kw / active_power_kw",
                    )

                result = self.pcs_service.set_active_power_kw(float(value), source=source)
                return self._pcs_command_response(request_id, command, result)

            if command == "PCS_SET_REACTIVE_POWER":
                if value is None:
                    value = command_packet.get("kvar", command_packet.get("reactive_power_kvar"))

                if value is None:
                    return self._response(
                        request_id=request_id,
                        command=command,
                        status="error",
                        message="PCS_SET_REACTIVE_POWER requires value / kvar / reactive_power_kvar",
                    )

                result = self.pcs_service.set_reactive_power_kvar(float(value), source=source)
                return self._pcs_command_response(request_id, command, result)

            if command == "PCS_RESET_FAULT":
                result = self.pcs_service.reset_fault(source=source)
                return self._pcs_command_response(request_id, command, result)

            if command == "PCS_HEARTBEAT":
                result = self.pcs_service.heartbeat(value=value, source=source)
                return self._pcs_command_response(request_id, command, result)

            return self._response(
                request_id=request_id,
                command=command,
                status="error",
                message=f"Unsupported PCS command: {command}",
            )

        except Exception as error:
            return self._response(
                request_id=request_id,
                command=command,
                status="error",
                message=str(error),
            )

    def _pcs_command_response(
        self,
        request_id: Optional[Any],
        command: str,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        pcs_status = str(result.get("status", "")).lower()

        ok_statuses = {"success", "ok"}

        response_status = "ok" if pcs_status in ok_statuses else "error"

        return self._response(
            request_id=request_id,
            command=command,
            status=response_status,
            message=result.get("description", "PCS command executed"),
            data=result,
        )

    # -------------------------------------------------
    # Status Packet
    # -------------------------------------------------

    def get_status_packet(self) -> Dict[str, Any]:
        return {
            "gateway_id": self.gateway_id,
            "timestamp": self._now(),
            "mode": "mock" if self.args.mock else "real",
            "chiller": {
                "enabled": self.chiller_enabled,
                "running": self.chiller_service is not None or self.mock_service is not None,
                "asset_id": self.asset_id,
            },
            "pcs": {
                "enabled": self.pcs_enabled,
                "running": self.pcs_service is not None,
                "asset_id": self.pcs_asset_id,
                "vendor": self.pcs_vendor,
                "host": self.pcs_host,
                "port": self.pcs_port,
                "unit_id": self.pcs_unit_id,
                "state": self.pcs_service.get_latest_state() if self.pcs_service else None,
            },
            "network": {
                "tcp_host": self.tcp_host,
                "tcp_port": self.tcp_port,
                "udp_pc_ip": self.pc_telemetry_ip,
                "udp_port": self.udp_telemetry_port,
            },
            "udp_streamer": self.udp_streamer.get_status() if self.udp_streamer else None,
            "tcp_server": self.tcp_server.get_status() if self.tcp_server else None,
            "log_http": {
                "enabled": self.enable_log_http_server and not self.args.no_log_http,
                "host": self.log_http_host,
                "port": self.log_http_port,
                "base_path": self.log_base_path,
            },
        }

    # -------------------------------------------------
    # Runtime Loop
    # -------------------------------------------------

    def run_forever(self) -> None:
        while self.running:
            time.sleep(1)

    # -------------------------------------------------
    # Shutdown
    # -------------------------------------------------

    def stop(self) -> None:
        print("\n[MAIN] Stopping EMS Gateway...")

        self.running = False

        if self.log_http_server is not None:
            try:
                self.log_http_server.stop()
            except Exception as error:
                print(f"[MAIN] Error while stopping HTTP log server: {error}")

        if self.tcp_server is not None:
            try:
                self.tcp_server.stop()
            except Exception as error:
                print(f"[MAIN] Error while stopping TCP server: {error}")

        if self.udp_streamer is not None:
            try:
                self.udp_streamer.stop()
            except Exception as error:
                print(f"[MAIN] Error while stopping UDP streamer: {error}")

        if self.pcs_service is not None:
            try:
                self.pcs_service.stop()
            except Exception as error:
                print(f"[MAIN] Error while stopping PCS service: {error}")

        if self.mock_service is not None:
            try:
                self.mock_service.stop_polling()
            except Exception as error:
                print(f"[MAIN] Error while stopping mock service: {error}")

        if self.chiller_service is not None:
            try:
                self.chiller_service.stop_polling()
            except Exception as error:
                print(f"[MAIN] Error while stopping chiller service: {error}")

        if self.chiller_driver is not None:
            try:
                self.chiller_driver.close()
            except Exception as error:
                print(f"[MAIN] Error while closing chiller Modbus driver: {error}")

        print("[MAIN] EMS Gateway stopped")

    # -------------------------------------------------
    # Banner
    # -------------------------------------------------

    def print_startup_banner(self) -> None:
        if self.args.mock:
            mode_text = "MOCK"
        else:
            active_assets = []
            if self.chiller_enabled:
                active_assets.append("CHILLER")
            if self.pcs_enabled:
                active_assets.append("PCS")
            mode_text = "REAL " + "+".join(active_assets) if active_assets else "REAL NONE"

        print("\n====================================================")
        print("          i.MX93 EMS Gateway Backend")
        print("====================================================")
        print(f"Gateway ID              : {self.gateway_id}")
        print(f"Mode                    : {mode_text}")
        print("")
        print("Chiller / Modbus RTU Configuration")
        print("----------------------------------------------------")
        print(f"Chiller Enabled         : {self.chiller_enabled and not self.args.mock}")
        print(f"Chiller Asset ID        : {self.asset_id}")
        print(f"Serial Port             : {self.modbus_port}")
        print(f"Slave ID                : {self.chiller_slave_id}")
        print(f"Baudrate                : {self.modbus_baudrate}")
        print(f"Serial Format           : {self.modbus_bytesize}{self.modbus_parity}{self.modbus_stopbits}")
        print(f"Timeout                 : {self.modbus_timeout} sec")
        print(f"Polling Interval        : {self.poll_interval_sec} sec")
        print("")
        print("PCS / Modbus TCP Configuration")
        print("----------------------------------------------------")
        print(f"PCS Enabled             : {self.pcs_enabled and not self.args.mock}")
        print(f"PCS Asset ID            : {self.pcs_asset_id}")
        print(f"PCS Vendor              : {self.pcs_vendor}")
        print(f"PCS Host                : {self.pcs_host}")
        print(f"PCS Port                : {self.pcs_port}")
        print(f"PCS Unit ID             : {self.pcs_unit_id}")
        print(f"PCS Timeout             : {self.pcs_timeout} sec")
        print(f"PCS Retries             : {self.pcs_retries}")
        print(f"PCS Poll Interval       : {self.pcs_poll_interval_sec} sec")
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
        print("")
        print("HTTP Log API Configuration")
        print("----------------------------------------------------")
        print(f"HTTP Log Enabled        : {self.enable_log_http_server and not self.args.no_log_http}")
        print(f"HTTP Log Host           : {self.log_http_host}")
        print(f"HTTP Log Port           : {self.log_http_port}")
        print(f"HTTP Log Base Path      : {self.log_base_path}")
        print(f"HTTP Log Max Rows       : {self.log_api_max_rows}")
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
        help="Run gateway in mock mode without Modbus/chiller/PCS hardware",
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
        "--pcs-host",
        default=None,
        help="Override PCS/ModSim IP address, example: 192.168.10.1",
    )

    parser.add_argument(
        "--pcs-port",
        type=int,
        default=None,
        help="Override PCS Modbus TCP port, example: 502",
    )

    parser.add_argument(
        "--pcs-unit",
        type=int,
        default=None,
        help="Override PCS Modbus unit ID, example: 1",
    )

    parser.add_argument(
        "--pcs-vendor",
        default=None,
        help="Override PCS vendor profile, example: njoy",
    )

    parser.add_argument(
        "--pcs-poll-interval",
        type=float,
        default=None,
        help="Override PCS polling interval in seconds",
    )

    parser.add_argument(
        "--no-chiller",
        action="store_true",
        help="Disable real chiller service",
    )

    parser.add_argument(
        "--no-pcs",
        action="store_true",
        help="Disable PCS service",
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

    parser.add_argument(
        "--no-log-http",
        action="store_true",
        help="Disable HTTP log API server",
    )

    parser.add_argument(
        "--log-http-port",
        type=int,
        default=None,
        help="Override HTTP log API server port",
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

    except Exception as error:
        print(f"[MAIN] Fatal error: {error}")
        app.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()