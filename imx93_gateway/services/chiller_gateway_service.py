"""
Chiller Gateway Service for i.MX93 EMS Gateway.

Role of this file:
- Uses ChillerModbusDriver to read/write chiller data.
- Maintains latest chiller state.
- Provides latest telemetry packet for UDP streaming.
- Executes control commands received from TCP server.
- Acts as the bridge between Modbus driver and network layer.

This file does not directly handle TCP or UDP sockets.
It only provides clean service APIs.
"""

import sys
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional


# -------------------------------------------------
# Import support
# -------------------------------------------------

CURRENT_FILE = Path(__file__).resolve()
IMX93_GATEWAY_DIR = CURRENT_FILE.parents[1]

if str(IMX93_GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(IMX93_GATEWAY_DIR))

try:
    from drivers.chiller_modbus_driver import ChillerModbusDriver
except ImportError:
    from imx93_gateway.drivers.chiller_modbus_driver import ChillerModbusDriver


class ChillerGatewayService:
    """
    Main service layer for chiller EMS gateway.

    Responsibilities:
    1. Poll chiller telemetry periodically
    2. Store latest chiller state
    3. Provide telemetry packet to UDP streamer
    4. Execute commands received from TCP server
    5. Return ACK/NACK responses
    """

    def __init__(
        self,
        driver: ChillerModbusDriver,
        gateway_id: str = "imx93_gateway_1",
        asset_id: str = "chiller_1",
        poll_interval_sec: float = 1.0,
    ):
        self.driver = driver
        self.gateway_id = gateway_id
        self.asset_id = asset_id
        self.poll_interval_sec = float(poll_interval_sec)

        self.latest_state: Optional[Any] = None
        self.latest_state_dict: Dict[str, Any] = {}
        self.last_poll_time: Optional[str] = None
        self.last_error: Optional[str] = None

        self._state_lock = threading.Lock()
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None

    # -------------------------------------------------
    # Utility Functions
    # -------------------------------------------------

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _object_to_dict(obj: Any) -> Dict[str, Any]:
        """
        Convert ChillerState object or dictionary into plain dictionary.
        """

        if obj is None:
            return {}

        if isinstance(obj, dict):
            return obj

        if hasattr(obj, "to_dict"):
            return obj.to_dict()

        try:
            return vars(obj)
        except Exception:
            return {"value": str(obj)}

    def _update_latest_state(self, state: Any) -> None:
        """
        Update latest chiller state safely.
        """

        state_dict = self._object_to_dict(state)

        with self._state_lock:
            self.latest_state = state
            self.latest_state_dict = state_dict
            self.last_poll_time = self._now()
            self.last_error = None

    def _set_error(self, error: Exception) -> None:
        """
        Store latest communication/error status.
        """

        with self._state_lock:
            self.last_error = str(error)
            self.last_poll_time = self._now()

            if self.latest_state_dict:
                self.latest_state_dict["communication_status"] = "error"
                self.latest_state_dict["last_error"] = str(error)

    # -------------------------------------------------
    # Polling APIs
    # -------------------------------------------------

    def poll_once(self) -> Dict[str, Any]:
        """
        Read chiller telemetry once using Modbus driver.
        """

        state = self.driver.read_all_parameters()
        self._update_latest_state(state)

        return self.get_latest_state_dict()

    def start_polling(self) -> None:
        """
        Start periodic Modbus polling in a background thread.
        """

        if self._running:
            print("[SERVICE] Polling already running")
            return

        self._running = True
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            name="ChillerPollingThread",
            daemon=True,
        )
        self._poll_thread.start()

        print("[SERVICE] Chiller polling started")

    def stop_polling(self) -> None:
        """
        Stop periodic Modbus polling.
        """

        self._running = False

        if self._poll_thread:
            self._poll_thread.join(timeout=2)

        print("[SERVICE] Chiller polling stopped")

    def _poll_loop(self) -> None:
        """
        Internal polling loop.
        """

        while self._running:
            try:
                state = self.driver.read_all_parameters()
                self._update_latest_state(state)

                print("[SERVICE] Chiller telemetry updated")

            except Exception as e:
                self._set_error(e)
                print(f"[SERVICE] Polling error: {e}")

            time.sleep(self.poll_interval_sec)

    # -------------------------------------------------
    # State / Telemetry APIs
    # -------------------------------------------------

    def get_latest_state_dict(self) -> Dict[str, Any]:
        """
        Return latest chiller state as plain dictionary.
        """

        with self._state_lock:
            return dict(self.latest_state_dict)

    def get_telemetry_packet(self) -> Dict[str, Any]:
        """
        Create final telemetry packet for UDP streamer.
        """

        with self._state_lock:
            data = dict(self.latest_state_dict)
            last_error = self.last_error
            last_poll_time = self.last_poll_time

        packet = {
            "type": "telemetry",
            "gateway_id": self.gateway_id,
            "asset_id": self.asset_id,
            "timestamp": self._now(),
            "last_poll_time": last_poll_time,
            "data": data,
        }

        if last_error:
            packet["status"] = "error"
            packet["error"] = last_error
        else:
            packet["status"] = "ok"

        return packet

    # -------------------------------------------------
    # Command Execution APIs
    # -------------------------------------------------

    def execute_command(self, command_packet: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute command received from TCP command server.

        Expected command packet examples:

        {
            "request_id": "REQ_001",
            "command": "READ_ALL"
        }

        {
            "request_id": "REQ_002",
            "command": "SET_TEMP",
            "value": 25.0
        }

        {
            "request_id": "REQ_003",
            "command": "SET_MODE",
            "value": 1
        }
        """

        request_id = command_packet.get("request_id")
        command = str(command_packet.get("command", "")).strip().upper()
        value = command_packet.get("value")
        verify = bool(command_packet.get("verify", True))

        try:
            if not command:
                raise ValueError("Missing command field")

            print(f"[SERVICE] Executing command: {command}, value={value}")

            # -----------------------------
            # Read Commands
            # -----------------------------

            if command == "READ_ALL":
                result = self.poll_once()

                return self._ok_response(
                    request_id=request_id,
                    command=command,
                    message="Chiller telemetry read successfully",
                    data=result,
                )

            if command == "READ_SETTINGS":
                result = self.driver.read_setting_parameters()

                return self._ok_response(
                    request_id=request_id,
                    command=command,
                    message="Chiller setting parameters read successfully",
                    data=result,
                )

            if command == "READ_MODE":
                result = self.driver.read_control_mode()

                return self._ok_response(
                    request_id=request_id,
                    command=command,
                    message="Chiller control mode read successfully",
                    data=result,
                )

            if command == "READ_TEMP":
                result = self.driver.read_set_temperature()

                return self._ok_response(
                    request_id=request_id,
                    command=command,
                    message="Chiller set temperature read successfully",
                    data=result,
                )

            if command == "READ_ONOFF":
                result = self.driver.read_on_off_enable()

                return self._ok_response(
                    request_id=request_id,
                    command=command,
                    message="Chiller ON/OFF status read successfully",
                    data=result,
                )

            # -----------------------------
            # Write / Control Commands
            # -----------------------------

            if command == "CHILLER_ON":
                result = self.driver.turn_on(verify=verify)

                return self._ok_response(
                    request_id=request_id,
                    command=command,
                    message="Chiller ON command executed",
                    data=result,
                )

            if command == "CHILLER_OFF":
                result = self.driver.turn_off(verify=verify)

                return self._ok_response(
                    request_id=request_id,
                    command=command,
                    message="Chiller OFF command executed",
                    data=result,
                )

            if command == "SET_TEMP":
                if value is None:
                    raise ValueError("SET_TEMP requires value field")

                result = self.driver.set_temperature(value, verify=verify)

                return self._ok_response(
                    request_id=request_id,
                    command=command,
                    message="Chiller set temperature command executed",
                    data=result,
                )

            if command == "SET_MODE":
                if value is None:
                    raise ValueError("SET_MODE requires value field")

                result = self.driver.set_control_mode(value, verify=verify)

                return self._ok_response(
                    request_id=request_id,
                    command=command,
                    message="Chiller set mode command executed",
                    data=result,
                )

            raise ValueError(f"Unsupported command: {command}")

        except Exception as e:
            print(f"[SERVICE] Command error: {e}")

            return self._error_response(
                request_id=request_id,
                command=command,
                message=str(e),
            )

    # -------------------------------------------------
    # Response Helpers
    # -------------------------------------------------

    def _ok_response(
        self,
        request_id: Optional[str],
        command: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "type": "response",
            "request_id": request_id,
            "timestamp": self._now(),
            "status": "ok",
            "command": command,
            "message": message,
            "data": data if data is not None else {},
        }

    def _error_response(
        self,
        request_id: Optional[str],
        command: str,
        message: str,
    ) -> Dict[str, Any]:
        return {
            "type": "response",
            "request_id": request_id,
            "timestamp": self._now(),
            "status": "error",
            "command": command,
            "message": message,
            "data": {},
        }


# -------------------------------------------------
# Standalone Test
# -------------------------------------------------

if __name__ == "__main__":
    driver = ChillerModbusDriver(
        port="/dev/ttyUSB0",
        slave_id=1,
    )

    if not driver.connect():
        print("[SERVICE TEST] Failed to connect to chiller")
        sys.exit(1)

    service = ChillerGatewayService(
        driver=driver,
        gateway_id="imx93_gateway_1",
        asset_id="chiller_1",
        poll_interval_sec=1.0,
    )

    try:
        print("\n[SERVICE TEST] Reading chiller once...")
        state = service.poll_once()
        print(state)

        print("\n[SERVICE TEST] Telemetry packet:")
        packet = service.get_telemetry_packet()
        print(packet)

        print("\n[SERVICE TEST] Testing READ_MODE command...")
        response = service.execute_command({
            "request_id": "TEST_001",
            "command": "READ_MODE"
        })
        print(response)

        print("\n[SERVICE TEST] Testing READ_TEMP command...")
        response = service.execute_command({
            "request_id": "TEST_002",
            "command": "READ_TEMP"
        })
        print(response)

    except Exception as e:
        print(f"[SERVICE TEST] Error: {e}")

    finally:
        driver.close()