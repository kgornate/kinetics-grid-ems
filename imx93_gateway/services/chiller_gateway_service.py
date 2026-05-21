"""
Chiller Gateway Service for i.MX93 EMS Gateway.

This service:
- Polls chiller telemetry from Modbus driver
- Adds setting/control fields into UDP telemetry
- Adds fault code description and bit analysis
- Provides latest telemetry packet for UDP streamer
- Executes TCP commands from PC / Flutter dashboard
"""

import sys
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional


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
    Service layer between:
    - ChillerModbusDriver
    - UDP telemetry streamer
    - TCP command server
    """

    FAULT_CODE_MAP = {
        0: "No fault",
    }

    MODE_READ_VALUE_MAP = {
        1: "Water pump circulation mode",
        2: "Refrigeration / Cooling mode",
        3: "Heating mode",
        4: "System automatic control mode",
    }

    def __init__(
        self,
        driver: ChillerModbusDriver,
        gateway_id: str = "imx93_gateway_1",
        asset_id: str = "chiller_1",
        poll_interval_sec: float = 1.0,
        include_settings_in_poll: bool = True,
    ):
        self.driver = driver
        self.gateway_id = gateway_id
        self.asset_id = asset_id
        self.poll_interval_sec = float(poll_interval_sec)
        self.include_settings_in_poll = include_settings_in_poll

        self.latest_state: Optional[Any] = None
        self.latest_state_dict: Dict[str, Any] = {}
        self.last_poll_time: Optional[str] = None
        self.last_error: Optional[str] = None

        self._state_lock = threading.Lock()
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _object_to_dict(obj: Any) -> Dict[str, Any]:
        if obj is None:
            return {}

        if isinstance(obj, dict):
            return dict(obj)

        if hasattr(obj, "to_dict"):
            return obj.to_dict()

        try:
            return vars(obj)
        except Exception:
            return {"value": str(obj)}

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    def _decode_fault(self, fault_code: Any) -> Dict[str, Any]:
        """
        Decode fault code.

        Current protocol PDF says:
            Fault alarm code -> See fault code sheet

        But the actual fault code sheet/table is not present in the uploaded PDF.

        Therefore:
        - 0 is safely mapped as "No fault"
        - Other values are reported as unmapped
        - Bit analysis is added because field value 42 can be interpreted as:
              42 decimal = 0b0000000000101010
              active bits = 1, 3, 5
          if the vendor uses a bitmask-style fault register.
        """

        try:
            code = int(fault_code)
        except Exception:
            return {
                "fault_code": fault_code,
                "fault_description": "Invalid fault code format",
                "fault_active": True,
                "fault_binary": None,
                "fault_active_bits": [],
                "fault_note": "Fault code is not an integer value.",
            }

        if code in self.FAULT_CODE_MAP:
            return {
                "fault_code": code,
                "fault_description": self.FAULT_CODE_MAP[code],
                "fault_active": code != 0,
                "fault_binary": format(code, "016b"),
                "fault_active_bits": [],
                "fault_note": "Mapped direct fault code.",
            }

        active_bits = [
            bit for bit in range(16)
            if code & (1 << bit)
        ]

        return {
            "fault_code": code,
            "fault_description": (
                f"Unmapped fault code {code}. "
                "Protocol refers to a separate fault code sheet."
            ),
            "fault_active": code != 0,
            "fault_binary": format(code, "016b"),
            "fault_active_bits": active_bits,
            "fault_note": (
                "If this register is bitmask-based, active bits indicate multiple alarms. "
                "Exact bit meanings need vendor fault code sheet."
            ),
        }

    def _merge_settings_into_telemetry(self, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add holding register information into live telemetry.

        Important:
        read_all_parameters() mainly reads input registers 0-11.
        But control mode, ON/OFF status, and set temperature are holding registers:

        - Register 200: Control mode
        - Register 201: ON/OFF enable
        - Register 205: Set temperature
        """

        if not self.include_settings_in_poll:
            return telemetry

        try:
            settings = self.driver.read_setting_parameters()

            control_mode = settings.get("control_mode", {})
            on_off = settings.get("on_off_enable", {})
            set_temp = settings.get("set_temperature", {})

            control_mode_raw = control_mode.get("raw_value")
            control_mode_text = control_mode.get("mode")

            if control_mode_text is None and control_mode_raw is not None:
                control_mode_text = self.MODE_READ_VALUE_MAP.get(
                    self._safe_int(control_mode_raw),
                    f"Unknown mode ({control_mode_raw})",
                )

            telemetry["control_mode_raw"] = control_mode_raw
            telemetry["control_mode"] = control_mode_text

            telemetry["on_off_raw"] = on_off.get("raw_value")
            telemetry["on_off_status"] = on_off.get("status")

            telemetry["set_temperature_raw"] = set_temp.get("raw_value")
            telemetry["set_temperature"] = set_temp.get("temperature_celsius")

            telemetry["settings_registers_200_to_208"] = settings.get(
                "raw_registers_200_to_208",
                [],
            )

        except Exception as e:
            telemetry["settings_read_error"] = str(e)

        return telemetry

    def _enhance_telemetry(self, state: Any) -> Dict[str, Any]:
        """
        Convert driver output into complete dashboard-ready telemetry.
        """

        telemetry = self._object_to_dict(state)

        fault_info = self._decode_fault(telemetry.get("fault_code", 0))
        telemetry.update(fault_info)

        telemetry = self._merge_settings_into_telemetry(telemetry)

        telemetry["communication_status"] = telemetry.get(
            "communication_status",
            "online",
        )

        return telemetry

    def _update_latest_state(self, state: Any) -> None:
        state_dict = self._enhance_telemetry(state)

        with self._state_lock:
            self.latest_state = state
            self.latest_state_dict = state_dict
            self.last_poll_time = self._now()
            self.last_error = None

    def _set_error(self, error: Exception) -> None:
        with self._state_lock:
            self.last_error = str(error)
            self.last_poll_time = self._now()

            if self.latest_state_dict:
                self.latest_state_dict["communication_status"] = "error"
                self.latest_state_dict["last_error"] = str(error)

    # -------------------------------------------------
    # Polling
    # -------------------------------------------------

    def poll_once(self) -> Dict[str, Any]:
        state = self.driver.read_all_parameters()
        self._update_latest_state(state)
        return self.get_latest_state_dict()

    def start_polling(self) -> None:
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
        self._running = False

        if self._poll_thread:
            self._poll_thread.join(timeout=2)

        print("[SERVICE] Chiller polling stopped")

    def _poll_loop(self) -> None:
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
    # Telemetry
    # -------------------------------------------------

    def get_latest_state_dict(self) -> Dict[str, Any]:
        with self._state_lock:
            return dict(self.latest_state_dict)

    def get_telemetry_packet(self) -> Dict[str, Any]:
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
    # TCP Command Execution
    # -------------------------------------------------

    def execute_command(self, command_packet: Dict[str, Any]) -> Dict[str, Any]:
        request_id = command_packet.get("request_id")
        command = str(command_packet.get("command", "")).strip().upper()
        value = command_packet.get("value")
        verify = bool(command_packet.get("verify", True))

        try:
            if not command:
                raise ValueError("Missing command field")

            print(f"[SERVICE] Executing command: {command}, value={value}")

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

            if command == "CHILLER_ON":
                result = self.driver.turn_on(verify=verify)

                try:
                    self.poll_once()
                except Exception:
                    pass

                return self._ok_response(
                    request_id=request_id,
                    command=command,
                    message="Chiller ON command executed",
                    data=result,
                )

            if command == "CHILLER_OFF":
                result = self.driver.turn_off(verify=verify)

                try:
                    self.poll_once()
                except Exception:
                    pass

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

                try:
                    self.poll_once()
                except Exception:
                    pass

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

                try:
                    self.poll_once()
                except Exception:
                    pass

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

    except Exception as e:
        print(f"[SERVICE TEST] Error: {e}")

    finally:
        driver.close()