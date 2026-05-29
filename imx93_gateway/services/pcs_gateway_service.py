#!/usr/bin/env python3
"""
PCS Gateway Service

Purpose:
- EMS-level service for PCS/Inverter asset.
- Maintains a persistent Modbus TCP connection.
- Polls PCS telemetry.
- Handles PCS control commands.
- Performs basic readback verification.

Current vendor support:
- njoy / enjoy 125kW PCS
- inpower / empower 125kW PCS
"""

import threading
import time
from typing import Any, Dict, Optional

from drivers.pcs_modbus_tcp_driver import PcsModbusTcpDriver
from drivers.pcs_profiles import njoy_125kw_profile as njoy
from drivers.pcs_profiles import inpower_125kw_profile as inpower
from models.pcs_state import PcsState


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
    ):
        self.asset_id = asset_id
        self.vendor = vendor.lower()
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.poll_interval_sec = poll_interval_sec
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

    def _load_profile(self, vendor: str):
        if vendor in ("njoy", "enjoy", "njoy_125kw", "enjoy_125kw"):
            return njoy

        if vendor in ("inpower", "empower", "inpower_125kw", "empower_125kw"):
            return inpower

        raise ValueError(f"Unsupported PCS vendor profile: {vendor}")

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

            return self._connected

        except Exception as exc:
            self._connected = False
            with self._lock:
                self.state.mark_offline(str(exc))
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
                return self.state.to_dict()

        except Exception as exc:
            error_msg = str(exc)

            self.disconnect()

            with self._lock:
                self.state.mark_offline(error_msg)
                latest = self.state.to_dict()

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

    def stop(self) -> None:
        """
        Stop background polling thread and close TCP connection.
        """
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=3.0)

        self.disconnect()

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            self.poll_once(raise_on_error=False)
            self._stop_event.wait(self.poll_interval_sec)

    def get_latest_state(self) -> Dict[str, Any]:
        """
        Return latest cached PCS state.
        """
        with self._lock:
            return self.state.to_dict()

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
            "vendor": self.vendor,
            "command": command,
            "status": status,
            "old_value": old_value,
            "new_value": new_value,
            "readback_value": readback_value,
            "description": description,
            "error": error,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    # ------------------------------------------------------------------
    # PCS commands
    # ------------------------------------------------------------------

    def power_on(self, verify: bool = True) -> Dict[str, Any]:
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

            return self._command_result(
                command=command,
                status=status,
                old_value=old_value,
                new_value=1,
                readback_value=readback,
                description="PCS power ON command written",
            )

        except Exception as exc:
            self.disconnect()
            return self._command_result(
                command=command,
                status="failed",
                new_value=1,
                error=str(exc),
                description="PCS power ON command failed",
            )

    def power_off(self, verify: bool = True) -> Dict[str, Any]:
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

            return self._command_result(
                command=command,
                status=status,
                old_value=old_value,
                new_value=0,
                readback_value=readback,
                description="PCS power OFF command written",
            )

        except Exception as exc:
            self.disconnect()
            return self._command_result(
                command=command,
                status="failed",
                new_value=0,
                error=str(exc),
                description="PCS power OFF command failed",
            )

    def set_active_power_kw(self, power_kw: float, verify: bool = True) -> Dict[str, Any]:
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

            return self._command_result(
                command=command,
                status=status,
                old_value=old_raw,
                new_value=expected_raw,
                readback_value=readback_raw,
                description=f"PCS active power setpoint written: {power_kw} kW",
            )

        except Exception as exc:
            self.disconnect()
            return self._command_result(
                command=command,
                status="failed",
                new_value=power_kw,
                error=str(exc),
                description="PCS active power command failed",
            )

    def set_reactive_power_kvar(self, reactive_power_kvar: float, verify: bool = True) -> Dict[str, Any]:
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

            return self._command_result(
                command=command,
                status=status,
                old_value=old_raw,
                new_value=expected_raw,
                readback_value=readback_raw,
                description=f"PCS reactive power setpoint written: {reactive_power_kvar} kvar",
            )

        except Exception as exc:
            self.disconnect()
            return self._command_result(
                command=command,
                status="failed",
                new_value=reactive_power_kvar,
                error=str(exc),
                description="PCS reactive power command failed",
            )

    def reset_fault(self) -> Dict[str, Any]:
        command = "reset_fault"

        try:
            with self._modbus_lock:
                self._ensure_connected()
                self.profile.reset_fault(self.driver)

            return self._command_result(
                command=command,
                status="success",
                new_value=1,
                description="PCS fault reset command written",
            )

        except Exception as exc:
            self.disconnect()
            return self._command_result(
                command=command,
                status="failed",
                new_value=1,
                error=str(exc),
                description="PCS fault reset command failed",
            )

    def heartbeat(self, value: Optional[int] = None, verify: bool = True) -> Dict[str, Any]:
        command = "heartbeat"

        if getattr(self.profile, "HEARTBEAT_SUPPORTED", True) is False:
            return self._command_result(
                command=command,
                status="unsupported",
                new_value=value,
                description=f"Heartbeat is not supported for vendor profile: {self.vendor}",
            )

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

            return self._command_result(
                command=command,
                status=status,
                new_value=value,
                readback_value=readback,
                description=f"PCS heartbeat written: {value}",
            )

        except Exception as exc:
            self.disconnect()
            return self._command_result(
                command=command,
                status="failed",
                new_value=value,
                error=str(exc),
                description="PCS heartbeat command failed",
            )

    def standby(self) -> Dict[str, Any]:
        command = "standby"

        if not hasattr(self.profile, "standby"):
            return self._command_result(
                command=command,
                status="unsupported",
                description=f"Standby command is not supported for vendor profile: {self.vendor}",
            )

        try:
            with self._modbus_lock:
                self._ensure_connected()
                self.profile.standby(self.driver)

            return self._command_result(
                command=command,
                status="success",
                new_value=1,
                description="PCS standby command written",
            )

        except Exception as exc:
            self.disconnect()
            return self._command_result(
                command=command,
                status="failed",
                new_value=1,
                error=str(exc),
                description="PCS standby command failed",
            )