#!/usr/bin/env python3
"""
PCS Gateway Service

Purpose:
- EMS-level service for PCS/Inverter asset.
- Maintains a persistent Modbus TCP connection.
- Polls PCS telemetry.
- Handles PCS control commands.
- Performs basic readback verification.
- Logs PCS telemetry, command events, and errors to eMMC/SD using StorageLogger.

Current vendor support:
- njoy / enjoy 125kW PCS
- inpower / empower 125kW PCS
"""

import sys
import threading
import time
from datetime import datetime
from pathlib import Path
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


from drivers.pcs_modbus_tcp_driver import PcsModbusTcpDriver
from drivers.pcs_profiles import njoy_125kw_profile as njoy
from drivers.pcs_profiles import inpower_125kw_profile as inpower
from models.pcs_state import PcsState
from services.storage_logger import StorageLogger


def get_config_value(name: str, default: Any) -> Any:
    if cfg is None:
        return default
    return getattr(cfg, name, default)


class PcsGatewayService:
    def __init__(
        self,
        asset_id: str = "pcs_1",
        vendor: str = "njoy",
        host: str = "192.168.10.1",
        port: int = 502,
        unit_id: int = 1,
        poll_interval_sec: float = 5.0,
        timeout: float = 3.0,
        retries: int = 2,
        gateway_id: str = "imx93_gateway_1",
        enable_storage_logging: Optional[bool] = None,
        log_base_path: Optional[str] = None,
        log_telemetry_interval_sec: Optional[float] = None,
    ):
        self.asset_id = asset_id
        self.gateway_id = gateway_id
        self.vendor = vendor.lower()
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.poll_interval_sec = float(poll_interval_sec)
        self.timeout = timeout
        self.retries = retries

        self.profile = self._load_profile(self.vendor)

        self.driver = PcsModbusTcpDriver(
            host=self.host,
            port=self.port,
            unit_id=self.unit_id,
            timeout=self.timeout,
            retries=self.retries,
        )

        self.state = PcsState(
            asset_id=self.asset_id,
            vendor=self.vendor,
        )

        self._lock = threading.Lock()
        self._modbus_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._connected = False

        self._heartbeat_counter = 0

        # -------------------------------------------------
        # Storage logger configuration
        # -------------------------------------------------

        if enable_storage_logging is None:
            enable_storage_logging = bool(get_config_value("ENABLE_STORAGE_LOGGING", False))

        self.enable_storage_logging = bool(enable_storage_logging)

        self.log_base_path = log_base_path or get_config_value(
            "LOG_BASE_PATH",
            "/home/root/ems_logs_test",
        )

        self.log_telemetry_interval_sec = float(
            log_telemetry_interval_sec
            if log_telemetry_interval_sec is not None
            else get_config_value(
                "PCS_LOG_TELEMETRY_INTERVAL_SEC",
                get_config_value("LOG_TELEMETRY_INTERVAL_SEC", 5.0),
            )
        )

        self.storage_logger: Optional[StorageLogger] = None
        self.last_storage_log_time = 0.0
        self._storage_logger_lock = threading.Lock()
        self._last_comm_status_for_event: Optional[str] = None

        self._initialize_storage_logger()

    def _load_profile(self, vendor: str):
        if vendor in ("njoy", "enjoy", "njoy_125kw", "enjoy_125kw"):
            return njoy

        if vendor in ("inpower", "empower", "inpower_125kw", "empower_125kw"):
            return inpower

        raise ValueError(f"Unsupported PCS vendor profile: {vendor}")

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _safe_str(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    # ------------------------------------------------------------------
    # Storage logging helpers
    # ------------------------------------------------------------------

    def _initialize_storage_logger(self) -> None:
        if not self.enable_storage_logging:
            print("[PCS STORAGE] Storage logging disabled from config")
            return

        try:
            self.storage_logger = StorageLogger(
                base_path=self.log_base_path,
                gateway_id=self.gateway_id,
                asset_id=self.asset_id,
                asset_type="pcs",
            )

            init_ok = self.storage_logger.initialize()

            if init_ok:
                print("[PCS STORAGE] PCS storage logger initialized successfully")
                print(f"[PCS STORAGE] Log base path: {self.log_base_path}")
                print(
                    f"[PCS STORAGE] Telemetry log interval: "
                    f"{self.log_telemetry_interval_sec} sec"
                )

                self._log_storage_event(
                    event_type="PCS_STORAGE_LOGGER_STARTED",
                    command="logger_start",
                    source="pcs_gateway_service.py",
                    status="success",
                    description="Storage logger initialized for PCS telemetry and command logging",
                )
            else:
                print("[PCS STORAGE] PCS storage logger initialization failed")

        except Exception as error:
            print(f"[PCS STORAGE] PCS storage logger initialization exception: {error}")
            self.storage_logger = None

    def _log_storage_event(
        self,
        event_type: str,
        command: str = "",
        old_value: Any = "",
        new_value: Any = "",
        readback_value: Any = "",
        source: str = "pcs_gateway_service.py",
        status: str = "success",
        description: str = "",
        error: str = "",
    ) -> None:
        if self.storage_logger is None:
            return

        try:
            with self._storage_logger_lock:
                self.storage_logger.log_event(
                    event_type=event_type,
                    command=self._safe_str(command),
                    old_value=self._safe_str(old_value),
                    new_value=self._safe_str(new_value),
                    readback_value=self._safe_str(readback_value),
                    vendor=self._safe_str(self._current_vendor_name()),
                    source=source,
                    status=status,
                    description=description,
                    error=error,
                )

        except Exception as log_error:
            print(f"[PCS STORAGE] Event logging exception: {log_error}")

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

        except Exception as log_error:
            print(f"[PCS STORAGE] Error logging exception: {log_error}")

    def _current_vendor_name(self) -> str:
        try:
            state = self.get_latest_state()
            return str(state.get("vendor") or getattr(self.profile, "VENDOR_NAME", self.vendor))
        except Exception:
            return str(getattr(self.profile, "VENDOR_NAME", self.vendor))

    def _get_storage_status(self) -> Dict[str, Any]:
        if self.storage_logger is None:
            return {
                "logger_status": "disabled_or_not_initialized",
                "base_path": self.log_base_path,
                "asset_id": self.asset_id,
            }

        try:
            return self.storage_logger.get_status()
        except Exception as error:
            return {
                "logger_status": "status_read_failed",
                "error": str(error),
                "base_path": self.log_base_path,
                "asset_id": self.asset_id,
            }

    def _log_latest_telemetry_if_due(self, force: bool = False) -> None:
        if self.storage_logger is None:
            return

        now = time.monotonic()

        if not force:
            if (now - self.last_storage_log_time) < self.log_telemetry_interval_sec:
                return

        with self._lock:
            telemetry = self.state.to_dict()

        if not telemetry:
            return

        try:
            with self._storage_logger_lock:
                status = self.storage_logger.log_telemetry(telemetry)

            if status:
                print("[PCS STORAGE] PCS telemetry logged to storage")
            else:
                print("[PCS STORAGE] PCS telemetry logging failed")

            self.last_storage_log_time = now

        except Exception as error:
            print(f"[PCS STORAGE] Telemetry logging exception: {error}")
            self._log_storage_error(
                error_type="PCS_STORAGE_TELEMETRY_LOG_EXCEPTION",
                error_source="pcs_gateway_service.py",
                description=str(error),
            )

    def _log_command_result(
        self,
        event_type: str,
        result: Dict[str, Any],
        source: str = "gateway",
    ) -> None:
        self._log_storage_event(
            event_type=event_type,
            command=str(result.get("command", "")),
            old_value=result.get("old_value", ""),
            new_value=result.get("new_value", ""),
            readback_value=result.get("readback_value", ""),
            source=source,
            status=str(result.get("status", "")),
            description=str(result.get("description", "")),
            error=str(result.get("error", "")),
        )

    def _log_comm_transition_if_needed(self, new_status: str, error: str = "") -> None:
        previous = self._last_comm_status_for_event

        if previous == new_status:
            return

        self._last_comm_status_for_event = new_status

        if previous is None:
            return

        self._log_storage_event(
            event_type="PCS_COMM_STATUS_CHANGED",
            command="comm_status",
            old_value=previous,
            new_value=new_status,
            source="pcs_gateway_service.py",
            status="success" if new_status == "online" else "error",
            description=f"PCS communication status changed from {previous} to {new_status}",
            error=error,
        )

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """
        Connect to PCS/ModSim over Modbus TCP.
        """
        if self._connected:
            return True

        try:
            ok = self.driver.connect()
            self._connected = bool(ok)

            if not self._connected:
                with self._lock:
                    self.state.mark_offline("Failed to connect to PCS/Simulator")
                self._log_comm_transition_if_needed("offline", "Failed to connect to PCS/Simulator")

            return self._connected

        except Exception as exc:
            self._connected = False
            with self._lock:
                self.state.mark_offline(str(exc))
            self._log_comm_transition_if_needed("offline", str(exc))
            return False

    def disconnect(self) -> None:
        """
        Close Modbus TCP connection.
        """
        try:
            self.driver.close()
        finally:
            self._connected = False

    def _ensure_connected(self) -> None:
        if self._connected:
            return

        if not self.connect():
            raise RuntimeError(
                f"Unable to connect to PCS/Simulator at {self.host}:{self.port}, unit={self.unit_id}"
            )

    def reconnect(self) -> bool:
        self.disconnect()
        time.sleep(0.3)
        return self.connect()

    # ------------------------------------------------------------------
    # Telemetry polling
    # ------------------------------------------------------------------

    def poll_once(self, raise_on_error: bool = False) -> Dict[str, Any]:
        """
        Read PCS telemetry once and update latest state.
        """
        try:
            with self._modbus_lock:
                self._ensure_connected()
                telemetry = self.profile.read_telemetry(self.driver)

            with self._lock:
                self.state.update_from_telemetry(telemetry)
                latest = self.state.to_dict()

            self._log_comm_transition_if_needed("online")
            self._log_latest_telemetry_if_due()
            return latest

        except Exception as exc:
            error_msg = str(exc)

            self.disconnect()

            with self._lock:
                self.state.mark_offline(error_msg)
                latest = self.state.to_dict()

            self._log_comm_transition_if_needed("offline", error_msg)
            self._log_storage_error(
                error_type="PCS_POLLING_ERROR",
                error_source="pcs_gateway_service.py",
                description=error_msg,
            )
            self._log_latest_telemetry_if_due()

            if raise_on_error:
                raise

            return latest

    def start(self) -> None:
        """
        Start background telemetry polling thread.
        """
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._poll_loop,
            name=f"PcsGatewayService-{self.asset_id}",
            daemon=True,
        )
        self._thread.start()

        self._log_storage_event(
            event_type="PCS_SERVICE_STARTED",
            command="service_start",
            source="pcs_gateway_service.py",
            status="success",
            description=(
                f"PCS service started for vendor={self.vendor}, "
                f"host={self.host}, port={self.port}, unit={self.unit_id}"
            ),
        )

    def stop(self) -> None:
        """
        Stop background polling thread and close TCP connection.
        """
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=3.0)

        self.disconnect()

        self._log_storage_event(
            event_type="PCS_SERVICE_STOPPED",
            command="service_stop",
            source="pcs_gateway_service.py",
            status="success",
            description="PCS gateway service polling stopped",
        )

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            self.poll_once(raise_on_error=False)
            self._stop_event.wait(self.poll_interval_sec)

    def get_latest_state(self) -> Dict[str, Any]:
        """
        Return latest cached PCS state.
        """
        with self._lock:
            state = self.state.to_dict()

        state["storage_logger"] = self._get_storage_status()
        return state

    # ------------------------------------------------------------------
    # Low-level readback helpers
    # ------------------------------------------------------------------

    def _read_holding_register_u16(self, address: int) -> int:
        self._ensure_connected()
        values = self.driver.read_holding_registers(address, 1)
        return int(values[0])

    def _read_holding_register_s16(self, address: int) -> int:
        raw = self._read_holding_register_u16(address)
        return PcsModbusTcpDriver.to_s16(raw)

    def _read_coil_bool(self, address: int) -> Optional[bool]:
        self._ensure_connected()
        values = self.driver.read_coils(address, 1)
        if not values:
            return None
        return bool(values[0])

    # ------------------------------------------------------------------
    # Command result helper
    # ------------------------------------------------------------------

    def _command_result(
        self,
        command: str,
        status: str,
        old_value: Any = None,
        new_value: Any = None,
        readback_value: Any = None,
        description: str = "",
        error: str = "",
    ) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "vendor": self._current_vendor_name(),
            "command": command,
            "status": status,
            "old_value": old_value,
            "new_value": new_value,
            "readback_value": readback_value,
            "description": description,
            "error": error,
            "timestamp": self._now(),
        }

    # ------------------------------------------------------------------
    # PCS commands
    # ------------------------------------------------------------------

    def power_on(self, verify: bool = True, source: str = "gateway") -> Dict[str, Any]:
        command = "power_on"

        try:
            with self._modbus_lock:
                self._ensure_connected()

                old_value = None

                if hasattr(self.profile, "REG_POWER_ON_OFF_COMMAND"):
                    try:
                        old_value = self._read_holding_register_s16(
                            self.profile.REG_POWER_ON_OFF_COMMAND
                        )
                    except Exception:
                        pass

                self.profile.power_on(self.driver)

                readback = None
                status = "success"

                verify_supported = getattr(
                    self.profile,
                    "POWER_COMMAND_VERIFY_SUPPORTED",
                    True,
                )

                if verify and verify_supported and hasattr(self.profile, "REG_POWER_ON_OFF_COMMAND"):
                    time.sleep(0.2)
                    readback = self._read_holding_register_s16(
                        self.profile.REG_POWER_ON_OFF_COMMAND
                    )
                    status = "success" if readback == 1 else "verification_failed"

            result = self._command_result(
                command=command,
                status=status,
                old_value=old_value,
                new_value=1,
                readback_value=readback,
                description="PCS power ON command written",
            )
            self._log_command_result("PCS_POWER_ON_WRITE", result, source=source)
            self._log_latest_telemetry_if_due(force=True)
            return result

        except Exception as exc:
            self.disconnect()
            result = self._command_result(
                command=command,
                status="failed",
                new_value=1,
                error=str(exc),
                description="PCS power ON command failed",
            )
            self._log_command_result("PCS_POWER_ON_WRITE", result, source=source)
            self._log_storage_error("PCS_COMMAND_FAILED", "pcs_gateway_service.py", str(exc))
            return result

    def power_off(self, verify: bool = True, source: str = "gateway") -> Dict[str, Any]:
        command = "power_off"

        try:
            with self._modbus_lock:
                self._ensure_connected()

                old_value = None

                if hasattr(self.profile, "REG_POWER_ON_OFF_COMMAND"):
                    try:
                        old_value = self._read_holding_register_s16(
                            self.profile.REG_POWER_ON_OFF_COMMAND
                        )
                    except Exception:
                        pass

                self.profile.power_off(self.driver)

                readback = None
                status = "success"

                verify_supported = getattr(
                    self.profile,
                    "POWER_COMMAND_VERIFY_SUPPORTED",
                    True,
                )

                if verify and verify_supported and hasattr(self.profile, "REG_POWER_ON_OFF_COMMAND"):
                    time.sleep(0.2)
                    readback = self._read_holding_register_s16(
                        self.profile.REG_POWER_ON_OFF_COMMAND
                    )
                    status = "success" if readback == 0 else "verification_failed"

            result = self._command_result(
                command=command,
                status=status,
                old_value=old_value,
                new_value=0,
                readback_value=readback,
                description="PCS power OFF command written",
            )
            self._log_command_result("PCS_POWER_OFF_WRITE", result, source=source)
            self._log_latest_telemetry_if_due(force=True)
            return result

        except Exception as exc:
            self.disconnect()
            result = self._command_result(
                command=command,
                status="failed",
                new_value=0,
                error=str(exc),
                description="PCS power OFF command failed",
            )
            self._log_command_result("PCS_POWER_OFF_WRITE", result, source=source)
            self._log_storage_error("PCS_COMMAND_FAILED", "pcs_gateway_service.py", str(exc))
            return result

    def set_active_power_kw(self, power_kw: float, verify: bool = True, source: str = "gateway") -> Dict[str, Any]:
        """
        Set active power.

        EMS convention:
        +ve kW = discharge/export
        -ve kW = charge/import

        Vendor profile converts the value into vendor-specific raw value.
        """
        command = "set_active_power_kw"

        try:
            expected_raw = self.profile.kw_to_raw(power_kw)

            with self._modbus_lock:
                self._ensure_connected()

                old_raw = None
                try:
                    old_raw = self._read_holding_register_s16(
                        self.profile.REG_ACTIVE_POWER_SETTING
                    )
                except Exception:
                    pass

                self.profile.set_active_power_kw(self.driver, power_kw)

                readback_raw = None
                status = "success"

                if verify:
                    time.sleep(0.2)
                    readback_raw = self._read_holding_register_s16(
                        self.profile.REG_ACTIVE_POWER_SETTING
                    )
                    status = "success" if readback_raw == expected_raw else "verification_failed"

            result = self._command_result(
                command=command,
                status=status,
                old_value=old_raw,
                new_value=expected_raw,
                readback_value=readback_raw,
                description=f"PCS active power setpoint written: {power_kw} kW",
            )
            self._log_command_result("PCS_ACTIVE_POWER_WRITE", result, source=source)
            self._log_latest_telemetry_if_due(force=True)
            return result

        except Exception as exc:
            self.disconnect()
            result = self._command_result(
                command=command,
                status="failed",
                new_value=power_kw,
                error=str(exc),
                description="PCS active power command failed",
            )
            self._log_command_result("PCS_ACTIVE_POWER_WRITE", result, source=source)
            self._log_storage_error("PCS_COMMAND_FAILED", "pcs_gateway_service.py", str(exc))
            return result

    def set_reactive_power_kvar(self, reactive_power_kvar: float, verify: bool = True, source: str = "gateway") -> Dict[str, Any]:
        command = "set_reactive_power_kvar"

        try:
            expected_raw = self.profile.kvar_to_raw(reactive_power_kvar)

            with self._modbus_lock:
                self._ensure_connected()

                old_raw = None
                try:
                    old_raw = self._read_holding_register_s16(
                        self.profile.REG_REACTIVE_POWER_SETTING
                    )
                except Exception:
                    pass

                self.profile.set_reactive_power_kvar(self.driver, reactive_power_kvar)

                readback_raw = None
                status = "success"

                if verify:
                    time.sleep(0.2)
                    readback_raw = self._read_holding_register_s16(
                        self.profile.REG_REACTIVE_POWER_SETTING
                    )
                    status = "success" if readback_raw == expected_raw else "verification_failed"

            result = self._command_result(
                command=command,
                status=status,
                old_value=old_raw,
                new_value=expected_raw,
                readback_value=readback_raw,
                description=f"PCS reactive power setpoint written: {reactive_power_kvar} kvar",
            )
            self._log_command_result("PCS_REACTIVE_POWER_WRITE", result, source=source)
            self._log_latest_telemetry_if_due(force=True)
            return result

        except Exception as exc:
            self.disconnect()
            result = self._command_result(
                command=command,
                status="failed",
                new_value=reactive_power_kvar,
                error=str(exc),
                description="PCS reactive power command failed",
            )
            self._log_command_result("PCS_REACTIVE_POWER_WRITE", result, source=source)
            self._log_storage_error("PCS_COMMAND_FAILED", "pcs_gateway_service.py", str(exc))
            return result

    def reset_fault(self, source: str = "gateway") -> Dict[str, Any]:
        command = "reset_fault"

        try:
            with self._modbus_lock:
                self._ensure_connected()
                self.profile.reset_fault(self.driver)

            result = self._command_result(
                command=command,
                status="success",
                new_value=1,
                description="PCS fault reset command written",
            )
            self._log_command_result("PCS_FAULT_RESET_WRITE", result, source=source)
            self._log_latest_telemetry_if_due(force=True)
            return result

        except Exception as exc:
            self.disconnect()
            result = self._command_result(
                command=command,
                status="failed",
                new_value=1,
                error=str(exc),
                description="PCS fault reset command failed",
            )
            self._log_command_result("PCS_FAULT_RESET_WRITE", result, source=source)
            self._log_storage_error("PCS_COMMAND_FAILED", "pcs_gateway_service.py", str(exc))
            return result

    def heartbeat(self, value: Optional[int] = None, verify: bool = True, source: str = "gateway") -> Dict[str, Any]:
        command = "heartbeat"

        if getattr(self.profile, "HEARTBEAT_SUPPORTED", True) is False:
            result = self._command_result(
                command=command,
                status="unsupported",
                new_value=value,
                description=f"Heartbeat is not supported for vendor profile: {self.vendor}",
            )
            self._log_command_result("PCS_HEARTBEAT_WRITE", result, source=source)
            return result

        try:
            with self._modbus_lock:
                self._ensure_connected()

                if value is None:
                    self._heartbeat_counter = (self._heartbeat_counter + 1) % 256
                    value = self._heartbeat_counter
                else:
                    value = int(value) % 256

                self.profile.write_heartbeat(self.driver, value)

                readback = None
                status = "success"

                if verify and hasattr(self.profile, "REG_HEARTBEAT"):
                    time.sleep(0.2)
                    readback = self._read_holding_register_s16(self.profile.REG_HEARTBEAT)
                    status = "success" if readback == value else "verification_failed"

            result = self._command_result(
                command=command,
                status=status,
                new_value=value,
                readback_value=readback,
                description=f"PCS heartbeat written: {value}",
            )
            self._log_command_result("PCS_HEARTBEAT_WRITE", result, source=source)
            return result

        except Exception as exc:
            self.disconnect()
            result = self._command_result(
                command=command,
                status="failed",
                new_value=value,
                error=str(exc),
                description="PCS heartbeat command failed",
            )
            self._log_command_result("PCS_HEARTBEAT_WRITE", result, source=source)
            self._log_storage_error("PCS_COMMAND_FAILED", "pcs_gateway_service.py", str(exc))
            return result

    def standby(self, source: str = "gateway") -> Dict[str, Any]:
        command = "standby"

        if not hasattr(self.profile, "standby"):
            result = self._command_result(
                command=command,
                status="unsupported",
                description=f"Standby command is not supported for vendor profile: {self.vendor}",
            )
            self._log_command_result("PCS_STANDBY_WRITE", result, source=source)
            return result

        try:
            with self._modbus_lock:
                self._ensure_connected()
                self.profile.standby(self.driver)

            result = self._command_result(
                command=command,
                status="success",
                new_value=1,
                description="PCS standby command written",
            )
            self._log_command_result("PCS_STANDBY_WRITE", result, source=source)
            self._log_latest_telemetry_if_due(force=True)
            return result

        except Exception as exc:
            self.disconnect()
            result = self._command_result(
                command=command,
                status="failed",
                new_value=1,
                error=str(exc),
                description="PCS standby command failed",
            )
            self._log_command_result("PCS_STANDBY_WRITE", result, source=source)
            self._log_storage_error("PCS_COMMAND_FAILED", "pcs_gateway_service.py", str(exc))
            return result
