"""
Chiller Gateway Service for i.MX93 EMS Gateway.

Purpose:
- Poll real chiller telemetry using Modbus RTU driver.
- Poll setting registers periodically.
- Provide UDP telemetry packets.
- Execute TCP commands from PC / Flutter dashboard.
- Prevent Modbus collision between polling thread and command thread.
- Log real chiller telemetry, events, and errors to eMMC/SD using StorageLogger.
- Log command events with both old_value and new_value.
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
    import config as cfg
except ImportError:
    cfg = None


try:
    from drivers.chiller_modbus_driver import ChillerModbusDriver
except ImportError:
    from imx93_gateway.drivers.chiller_modbus_driver import ChillerModbusDriver


try:
    from services.storage_logger import StorageLogger
except ImportError:
    from imx93_gateway.services.storage_logger import StorageLogger


def get_config_value(name: str, default: Any) -> Any:
    if cfg is None:
        return default

    return getattr(cfg, name, default)


class ChillerGatewayService:
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
        settings_poll_interval_sec: float = 5.0,
        include_settings_in_poll: bool = True,
    ):
        self.driver = driver
        self.gateway_id = gateway_id
        self.asset_id = asset_id

        self.poll_interval_sec = float(poll_interval_sec)
        self.settings_poll_interval_sec = float(settings_poll_interval_sec)
        self.include_settings_in_poll = include_settings_in_poll

        self.latest_state: Optional[Any] = None
        self.latest_state_dict: Dict[str, Any] = {}
        self.latest_settings_dict: Dict[str, Any] = {}

        self.last_poll_time: Optional[str] = None
        self.last_settings_poll_time: Optional[str] = None
        self.last_error: Optional[str] = None
        self.last_settings_error: Optional[str] = None

        self._state_lock = threading.Lock()

        # This lock protects full Modbus command sequences.
        # Polling and TCP command execution must not access RS485 at the same time.
        self._modbus_sequence_lock = threading.Lock()

        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._last_settings_poll_monotonic = 0.0

        # -------------------------------------------------
        # Storage logger configuration
        # -------------------------------------------------

        self.enable_storage_logging = bool(
            get_config_value("ENABLE_STORAGE_LOGGING", False)
        )

        self.log_base_path = get_config_value(
            "LOG_BASE_PATH",
            "/home/root/ems_logs_test",
        )

        self.log_telemetry_interval_sec = float(
            get_config_value("LOG_TELEMETRY_INTERVAL_SEC", 5.0)
        )

        self.storage_logger: Optional[StorageLogger] = None
        self.last_storage_log_time = 0.0
        self._storage_logger_lock = threading.Lock()

        self._initialize_storage_logger()

    # -------------------------------------------------
    # Utility
    # -------------------------------------------------

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

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
        try:
            code = int(fault_code)
        except Exception:
            return {
                "fault_code": fault_code,
                "fault_description": "Invalid fault code format",
                "fault_active": True,
                "fault_binary": None,
                "fault_active_bits": [],
            }

        if code in self.FAULT_CODE_MAP:
            return {
                "fault_code": code,
                "fault_description": self.FAULT_CODE_MAP[code],
                "fault_active": code != 0,
                "fault_binary": format(code, "016b"),
                "fault_active_bits": [],
            }

        active_bits = [bit for bit in range(16) if code & (1 << bit)]

        return {
            "fault_code": code,
            "fault_description": (
                f"Unmapped fault code {code}. "
                "Protocol refers to separate fault code sheet."
            ),
            "fault_active": code != 0,
            "fault_binary": format(code, "016b"),
            "fault_active_bits": active_bits,
        }

    # -------------------------------------------------
    # Storage Logger
    # -------------------------------------------------

    def _initialize_storage_logger(self) -> None:
        if not self.enable_storage_logging:
            print("[STORAGE] Storage logging disabled from config")
            return

        try:
            self.storage_logger = StorageLogger(
                base_path=self.log_base_path,
                gateway_id=self.gateway_id,
                asset_id=self.asset_id,
            )

            init_ok = self.storage_logger.initialize()

            if init_ok:
                print("[STORAGE] Storage logger initialized successfully")
                print(f"[STORAGE] Log base path: {self.log_base_path}")
                print(
                    f"[STORAGE] Telemetry log interval: "
                    f"{self.log_telemetry_interval_sec} sec"
                )

                self._log_storage_event(
                    event_type="STORAGE_LOGGER_STARTED",
                    source="chiller_gateway_service.py",
                    status="success",
                    description=(
                        "Storage logger initialized for real chiller telemetry logging"
                    ),
                )
            else:
                print("[STORAGE] Storage logger initialization failed")

        except Exception as error:
            print(f"[STORAGE] Storage logger initialization exception: {error}")
            self.storage_logger = None

    def _log_storage_event(
        self,
        event_type: str,
        old_value: str = "",
        new_value: str = "",
        source: str = "chiller_gateway_service.py",
        status: str = "success",
        description: str = "",
    ) -> None:
        if self.storage_logger is None:
            return

        try:
            with self._storage_logger_lock:
                self.storage_logger.log_event(
                    event_type=event_type,
                    old_value=old_value,
                    new_value=new_value,
                    source=source,
                    status=status,
                    description=description,
                )

        except Exception as error:
            print(f"[STORAGE] Event logging exception: {error}")

    def _log_storage_error(
        self,
        error_type: str,
        error_source: str,
        description: str,
    ) -> None:
        if self.storage_logger is None:
            return

        try:
            with self._storage_logger_lock:
                self.storage_logger.log_error(
                    error_type=error_type,
                    error_source=error_source,
                    description=description,
                )

        except Exception as error:
            print(f"[STORAGE] Error logging exception: {error}")

    def _get_storage_status(self) -> Dict[str, Any]:
        if self.storage_logger is None:
            return {
                "logger_status": "disabled_or_not_initialized",
                "base_path": self.log_base_path,
            }

        try:
            return self.storage_logger.get_status()
        except Exception as error:
            return {
                "logger_status": "status_read_failed",
                "error": str(error),
                "base_path": self.log_base_path,
            }

    def _read_old_value_for_command_unlocked(self, command: str) -> str:
        """
        Reads the current value before executing a write command.

        Caller must hold _modbus_sequence_lock.
        If old value read fails, command execution should still continue.
        """

        try:
            if command == "SET_TEMP":
                result = self.driver.read_set_temperature()

                if isinstance(result, dict):
                    if "temperature_celsius" in result:
                        return str(result.get("temperature_celsius"))
                    if "raw_value" in result:
                        return str(result.get("raw_value"))

                return str(result)

            if command == "SET_MODE":
                result = self.driver.read_control_mode()

                if isinstance(result, dict):
                    mode = result.get("mode")
                    raw_value = result.get("raw_value")

                    if mode is not None and raw_value is not None:
                        return f"{mode} ({raw_value})"

                    if mode is not None:
                        return str(mode)

                    if raw_value is not None:
                        return str(raw_value)

                return str(result)

            if command in ["CHILLER_ON", "CHILLER_OFF"]:
                result = self.driver.read_on_off_enable()

                if isinstance(result, dict):
                    status = result.get("status")
                    raw_value = result.get("raw_value")

                    if status is not None and raw_value is not None:
                        return f"{status} ({raw_value})"

                    if status is not None:
                        return str(status)

                    if raw_value is not None:
                        return str(raw_value)

                return str(result)

            return ""

        except Exception as error:
            print(f"[SERVICE] Old value read failed for {command}: {error}")

            self._log_storage_error(
                error_type="OLD_VALUE_READ_FAILED",
                error_source="chiller_gateway_service.py",
                description=f"command={command}; error={error}",
            )

            return "unknown"

    def convert_telemetry_for_logging(self, telemetry: Any) -> Dict[str, Any]:
        """
        Converts real chiller telemetry into StorageLogger dictionary format.

        Supports:
        - dict-based telemetry
        - object-based telemetry
        - existing driver field names
        - merged settings fields
        """

        data = self._object_to_dict(telemetry)

        if not data:
            return {
                "system_on_off": "unknown",
                "control_mode": "unknown",
                "set_temperature": "unknown",
                "outlet_water_temp": "unknown",
                "return_water_temp": "unknown",
                "outlet_water_pressure": "unknown",
                "return_water_pressure": "unknown",
                "ambient_temp": "unknown",
                "water_pump_status": "unknown",
                "compressor_1_status": "unknown",
                "compressor_2_status": "unknown",
                "electric_heater_status": "unknown",
                "condensate_fan_status": "unknown",
                "modbus_status": "failed",
            }

        system_on_off = data.get(
            "system_on_off",
            data.get(
                "on_off_status",
                data.get("system_status", "unknown"),
            ),
        )

        control_mode = data.get(
            "control_mode",
            data.get("control_mode_raw", "unknown"),
        )

        set_temperature = data.get(
            "set_temperature",
            data.get("set_temperature_celsius", "unknown"),
        )

        return {
            "system_on_off": system_on_off,
            "control_mode": control_mode,
            "set_temperature": set_temperature,
            "outlet_water_temp": data.get(
                "outlet_water_temp",
                data.get("outlet_water_temperature", "unknown"),
            ),
            "return_water_temp": data.get(
                "return_water_temp",
                data.get(
                    "inlet_water_temp",
                    data.get("return_water_temperature", "unknown"),
                ),
            ),
            "outlet_water_pressure": data.get(
                "outlet_water_pressure",
                "unknown",
            ),
            "return_water_pressure": data.get(
                "return_water_pressure",
                data.get("inlet_water_pressure", "unknown"),
            ),
            "ambient_temp": data.get(
                "ambient_temp",
                data.get("ambient_temperature", "unknown"),
            ),
            "water_pump_status": data.get(
                "water_pump_status",
                data.get("water_pump", "unknown"),
            ),
            "compressor_1_status": data.get(
                "compressor_1_status",
                data.get("compressor1", data.get("compressor_1", "unknown")),
            ),
            "compressor_2_status": data.get(
                "compressor_2_status",
                data.get("compressor2", data.get("compressor_2", "unknown")),
            ),
            "electric_heater_status": data.get(
                "electric_heater_status",
                data.get("electric_heater", "unknown"),
            ),
            "condensate_fan_status": data.get(
                "condensate_fan_status",
                data.get("condensate_fan", "unknown"),
            ),
            "modbus_status": data.get(
                "modbus_status",
                data.get("communication_status", "OK"),
            ),
        }

    def _log_latest_telemetry_if_due(self, force: bool = False) -> None:
        if self.storage_logger is None:
            return

        now = time.monotonic()

        if not force:
            if (now - self.last_storage_log_time) < self.log_telemetry_interval_sec:
                return

        with self._state_lock:
            telemetry = dict(self.latest_state_dict)

        if not telemetry:
            return

        log_data = self.convert_telemetry_for_logging(telemetry)

        try:
            with self._storage_logger_lock:
                status = self.storage_logger.log_telemetry(log_data)

            if status:
                print("[STORAGE] Real chiller telemetry logged to storage")
            else:
                print("[STORAGE] Real chiller telemetry logging failed")

            self.last_storage_log_time = now

        except Exception as error:
            print(f"[STORAGE] Telemetry logging exception: {error}")
            self._log_storage_error(
                error_type="STORAGE_TELEMETRY_LOG_EXCEPTION",
                error_source="chiller_gateway_service.py",
                description=str(error),
            )

    def _log_command_event(
        self,
        command: str,
        old_value: Any,
        new_value: Any,
        response_status: str,
        response_message: str,
        result: Optional[Dict[str, Any]],
        client: str = "unknown",
    ) -> None:
        event_type_map = {
            "CHILLER_ON": "SYSTEM_ON_OFF_WRITE",
            "CHILLER_OFF": "SYSTEM_ON_OFF_WRITE",
            "SET_TEMP": "SET_TEMPERATURE_WRITE",
            "SET_MODE": "CONTROL_MODE_WRITE",
        }

        event_type = event_type_map.get(command)

        if event_type is None:
            return

        description = (
            f"command={command}; client={client}; "
            f"message={response_message}; result={result}"
        )

        self._log_storage_event(
            event_type=event_type,
            old_value=str(old_value),
            new_value=str(new_value),
            source="flutter_tcp_command",
            status=response_status,
            description=description,
        )

    # -------------------------------------------------
    # Settings polling / merging
    # -------------------------------------------------

    def _should_poll_settings(self) -> bool:
        if not self.include_settings_in_poll:
            return False

        now = time.monotonic()
        return (
            now - self._last_settings_poll_monotonic
        ) >= self.settings_poll_interval_sec

    def _read_settings_unlocked(self) -> Dict[str, Any]:
        """
        Read setting registers.

        Caller must hold _modbus_sequence_lock.
        """

        print("[SERVICE] Reading setting registers 200-208...")
        settings = self.driver.read_setting_parameters()

        with self._state_lock:
            self.latest_settings_dict = dict(settings)
            self.last_settings_poll_time = self._now()
            self.last_settings_error = None

        self._last_settings_poll_monotonic = time.monotonic()
        print(f"[SERVICE] Settings updated: {settings}")

        return settings

    def _read_settings_if_due_unlocked(self) -> None:
        """
        Read settings only if interval has elapsed.

        Caller must hold _modbus_sequence_lock.
        """

        if not self._should_poll_settings():
            return

        try:
            self._read_settings_unlocked()

        except Exception as error:
            with self._state_lock:
                self.last_settings_error = str(error)

            self._last_settings_poll_monotonic = time.monotonic()
            print(f"[SERVICE] Settings read error: {error}")

            self._log_storage_error(
                error_type="SETTINGS_READ_FAILED",
                error_source="chiller_gateway_service.py",
                description=str(error),
            )

    def _merge_cached_settings_into_telemetry(
        self,
        telemetry: Dict[str, Any],
    ) -> Dict[str, Any]:
        with self._state_lock:
            settings = dict(self.latest_settings_dict)
            settings_error = self.last_settings_error
            settings_time = self.last_settings_poll_time

        if settings:
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

        telemetry["last_settings_poll_time"] = settings_time

        if settings_error:
            telemetry["settings_read_error"] = settings_error

        return telemetry

    # -------------------------------------------------
    # Telemetry enhancement
    # -------------------------------------------------

    def _enhance_telemetry(self, state: Any) -> Dict[str, Any]:
        telemetry = self._object_to_dict(state)

        fault_info = self._decode_fault(telemetry.get("fault_code", 0))
        telemetry.update(fault_info)

        telemetry = self._merge_cached_settings_into_telemetry(telemetry)

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

        self._log_storage_error(
            error_type="MODBUS_OR_POLLING_ERROR",
            error_source="chiller_gateway_service.py",
            description=str(error),
        )

    # -------------------------------------------------
    # Polling
    # -------------------------------------------------

    def poll_once(self) -> Dict[str, Any]:
        """
        One complete polling cycle.

        Protected with sequence lock to avoid collision with TCP commands.
        """

        with self._modbus_sequence_lock:
            self._read_settings_if_due_unlocked()
            state = self.driver.read_all_parameters()
            self._update_latest_state(state)

        self._log_latest_telemetry_if_due()

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

        self._log_storage_event(
            event_type="STORAGE_LOGGER_STOPPED",
            source="chiller_gateway_service.py",
            status="success",
            description="Chiller gateway service polling stopped",
        )

        print("[SERVICE] Chiller polling stopped")

    def _poll_loop(self) -> None:
        while self._running:
            try:
                with self._modbus_sequence_lock:
                    self._read_settings_if_due_unlocked()
                    state = self.driver.read_all_parameters()
                    self._update_latest_state(state)

                print("[SERVICE] Chiller telemetry updated")

                # Storage logging happens outside the Modbus lock.
                # This avoids blocking RS485 communication because of file I/O.
                self._log_latest_telemetry_if_due()

            except Exception as error:
                self._set_error(error)
                print(f"[SERVICE] Polling error: {error}")

            time.sleep(self.poll_interval_sec)

    # -------------------------------------------------
    # Telemetry packet
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
            "storage_logger": self._get_storage_status(),
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
        client = str(command_packet.get("client", "unknown"))

        try:
            if not command:
                raise ValueError("Missing command field")

            print(f"[SERVICE] Executing command: {command}, value={value}")

            with self._modbus_sequence_lock:
                if command == "READ_ALL":
                    self._read_settings_if_due_unlocked()
                    state = self.driver.read_all_parameters()
                    self._update_latest_state(state)

                    self._log_latest_telemetry_if_due(force=True)

                    result = self.get_latest_state_dict()

                    return self._ok_response(
                        request_id,
                        command,
                        "Chiller telemetry read successfully",
                        result,
                    )

                if command == "READ_SETTINGS":
                    result = self._read_settings_unlocked()
                    return self._ok_response(
                        request_id,
                        command,
                        "Chiller setting parameters read successfully",
                        result,
                    )

                if command == "READ_MODE":
                    result = self.driver.read_control_mode()
                    return self._ok_response(
                        request_id,
                        command,
                        "Chiller control mode read successfully",
                        result,
                    )

                if command == "READ_TEMP":
                    result = self.driver.read_set_temperature()
                    return self._ok_response(
                        request_id,
                        command,
                        "Chiller set temperature read successfully",
                        result,
                    )

                if command == "READ_ONOFF":
                    result = self.driver.read_on_off_enable()
                    return self._ok_response(
                        request_id,
                        command,
                        "Chiller ON/OFF status read successfully",
                        result,
                    )

                if command == "CHILLER_ON":
                    old_value = self._read_old_value_for_command_unlocked(command)

                    result = self.driver.turn_on(verify=verify)
                    self._post_command_refresh_unlocked()

                    message = "Chiller ON command executed"

                    self._log_command_event(
                        command=command,
                        old_value=old_value,
                        new_value="ON (1)",
                        response_status="success",
                        response_message=message,
                        result=result,
                        client=client,
                    )

                    self._log_latest_telemetry_if_due(force=True)

                    return self._ok_response(
                        request_id,
                        command,
                        message,
                        result,
                    )

                if command == "CHILLER_OFF":
                    old_value = self._read_old_value_for_command_unlocked(command)

                    result = self.driver.turn_off(verify=verify)
                    self._post_command_refresh_unlocked()

                    message = "Chiller OFF command executed"

                    self._log_command_event(
                        command=command,
                        old_value=old_value,
                        new_value="OFF (0)",
                        response_status="success",
                        response_message=message,
                        result=result,
                        client=client,
                    )

                    self._log_latest_telemetry_if_due(force=True)

                    return self._ok_response(
                        request_id,
                        command,
                        message,
                        result,
                    )

                if command == "SET_TEMP":
                    if value is None:
                        raise ValueError("SET_TEMP requires value field")

                    old_value = self._read_old_value_for_command_unlocked(command)

                    result = self.driver.set_temperature(value, verify=verify)
                    self._post_command_refresh_unlocked()

                    message = "Chiller set temperature command executed"

                    self._log_command_event(
                        command=command,
                        old_value=old_value,
                        new_value=value,
                        response_status="success",
                        response_message=message,
                        result=result,
                        client=client,
                    )

                    self._log_latest_telemetry_if_due(force=True)

                    return self._ok_response(
                        request_id,
                        command,
                        message,
                        result,
                    )

                if command == "SET_MODE":
                    if value is None:
                        raise ValueError("SET_MODE requires value field")

                    print(f"[SERVICE] SET_MODE requested GUI/write value: {value}")

                    old_value = self._read_old_value_for_command_unlocked(command)

                    result = self.driver.set_control_mode(value, verify=verify)

                    print(f"[SERVICE] SET_MODE driver result: {result}")

                    time.sleep(0.5)
                    self._post_command_refresh_unlocked()

                    verified = bool(result.get("verified", False))

                    if not verified:
                        message = (
                            "SET_MODE command sent, but readback verification failed. "
                            "Check chiller mode permissions/state."
                        )

                        self._log_command_event(
                            command=command,
                            old_value=old_value,
                            new_value=value,
                            response_status="warning",
                            response_message=message,
                            result=result,
                            client=client,
                        )

                        self._log_latest_telemetry_if_due(force=True)

                        return self._warning_response(
                            request_id=request_id,
                            command=command,
                            message=message,
                            data=result,
                        )

                    message = "Chiller set mode command executed and verified"

                    self._log_command_event(
                        command=command,
                        old_value=old_value,
                        new_value=value,
                        response_status="success",
                        response_message=message,
                        result=result,
                        client=client,
                    )

                    self._log_latest_telemetry_if_due(force=True)

                    return self._ok_response(
                        request_id,
                        command,
                        message,
                        result,
                    )

                raise ValueError(f"Unsupported command: {command}")

        except Exception as error:
            print(f"[SERVICE] Command error: {error}")

            self._log_storage_error(
                error_type="COMMAND_EXECUTION_FAILED",
                error_source="chiller_gateway_service.py",
                description=f"command={command}; value={value}; error={error}",
            )

            self._log_command_event(
                command=command,
                old_value="unknown",
                new_value=value,
                response_status="error",
                response_message=str(error),
                result={},
                client=client,
            )

            return self._error_response(request_id, command, str(error))

    def _post_command_refresh_unlocked(self) -> None:
        """
        Refresh settings + telemetry after a write command.

        Caller must hold _modbus_sequence_lock.
        """

        try:
            time.sleep(0.3)
            self._read_settings_unlocked()
            state = self.driver.read_all_parameters()
            self._update_latest_state(state)

        except Exception as error:
            with self._state_lock:
                self.last_settings_error = str(error)

            print(f"[SERVICE] Post-command refresh error: {error}")

            self._log_storage_error(
                error_type="POST_COMMAND_REFRESH_FAILED",
                error_source="chiller_gateway_service.py",
                description=str(error),
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

    def _warning_response(
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
            "status": "warning",
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
    driver = ChillerModbusDriver(port="/dev/ttyUSB0", slave_id=1)

    if not driver.connect():
        print("[SERVICE TEST] Failed to connect to chiller")
        sys.exit(1)

    service = ChillerGatewayService(driver=driver)

    try:
        print(service.poll_once())
        print(service.get_telemetry_packet())
    finally:
        driver.close()