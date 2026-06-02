"""
BMS / BCU Gateway Service - Kinetics Grid EMS Gateway

Purpose:
- Asset-level service for BMS/BCU integration in Kinetics Grid EMS.
- Uses drivers/bms_modbus_tcp_driver.py for Modbus TCP communication.
- Maintains latest EMS-facing BMS state using models/bms_state.py.
- Provides clean APIs for main.py, UDP telemetry streamer, TCP command server,
  storage logging, and Flutter dashboard.

Design rules:
- No Modbus register addresses are defined here.
- Register addresses/scaling/bitfields live only in drivers/bms_register_map.py.
- Driver handles protocol read/write.
- This service handles polling, state, commands, alarm transitions and optional logging.

Typical usage from main.py:

    from services.bms_gateway_service import BmsGatewayService, BmsServiceConfig

    bms_service = BmsGatewayService(
        BmsServiceConfig(
            host=BMS_MODBUS_HOST,
            port=BMS_MODBUS_PORT,
            unit_id=BMS_UNIT_ID,
            gateway_id=GATEWAY_ID,
            asset_id=BMS_ASSET_ID,
        ),
        storage_logger=storage_logger,
    )
    bms_service.start()

    latest = bms_service.get_latest_state_dict()
    result = bms_service.execute_command("START_BMS_PRECHARGE")
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set

try:
    from drivers.bms_register_map import (
        BMS_ASSET_ID,
        BMS_DEFAULT_HOST,
        BMS_DEFAULT_PORT,
        BMS_DEFAULT_UNIT_ID,
    )
    from drivers.bms_modbus_tcp_driver import BmsDriverConfig, BmsModbusTcpDriver
    from models.bms_state import BMS_LOG_FIELDS, DEFAULT_GATEWAY_ID, BmsState, utc_now_iso
except ImportError:  # pragma: no cover - allows direct local testing from copied files
    from bms_register_map import (  # type: ignore
        BMS_ASSET_ID,
        BMS_DEFAULT_HOST,
        BMS_DEFAULT_PORT,
        BMS_DEFAULT_UNIT_ID,
    )
    from bms_modbus_tcp_driver import BmsDriverConfig, BmsModbusTcpDriver  # type: ignore
    from bms_state import BMS_LOG_FIELDS, DEFAULT_GATEWAY_ID, BmsState, utc_now_iso  # type: ignore


@dataclass
class BmsServiceConfig:
    """Configuration for BMS gateway service."""

    gateway_id: str = DEFAULT_GATEWAY_ID
    asset_id: str = BMS_ASSET_ID

    host: str = BMS_DEFAULT_HOST
    port: int = BMS_DEFAULT_PORT
    unit_id: int = BMS_DEFAULT_UNIT_ID
    timeout: float = 2.0
    address_offset: int = 0

    poll_interval_sec: float = 1.0
    command_verify_delay_sec: float = 0.3
    communication_lost_after_sec: float = 5.0

    enable_storage_logging: bool = True
    telemetry_log_interval_sec: float = 5.0
    print_status: bool = True


class BmsGatewayService:
    """Threaded BMS/BCU asset service."""

    def __init__(
        self,
        config: Optional[BmsServiceConfig] = None,
        driver: Optional[BmsModbusTcpDriver] = None,
        storage_logger: Optional[Any] = None,
    ):
        self.config = config or BmsServiceConfig()
        self.driver = driver or BmsModbusTcpDriver(
            BmsDriverConfig(
                host=self.config.host,
                port=self.config.port,
                unit_id=self.config.unit_id,
                timeout=self.config.timeout,
                address_offset=self.config.address_offset,
            )
        )
        self.storage_logger = storage_logger

        self._lock = threading.RLock()
        self._modbus_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self.latest_state: BmsState = BmsState(
            gateway_id=self.config.gateway_id,
            asset_id=self.config.asset_id,
            communication_status="unknown",
        )

        self._last_log_ts: float = 0.0
        self._last_seen_online: bool = False
        self._last_alarm_set: Set[str] = set()
        self._started: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start BMS background polling."""
        if self._started:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="BmsGatewayService", daemon=True)
        self._thread.start()
        self._started = True
        if self.config.print_status:
            print(
                f"[BMS] Service started for {self.config.asset_id} "
                f"at {self.config.host}:{self.config.port}, unit_id={self.config.unit_id}"
            )

    def stop(self) -> None:
        """Stop BMS background polling and close Modbus connection."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self.driver.close()
        self._started = False
        if self.config.print_status:
            print("[BMS] Service stopped")

    def is_running(self) -> bool:
        return self._started and self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------
    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            loop_start = time.time()
            try:
                self.poll_once()
            except Exception as exc:  # poll_once already handles most errors; keep loop alive.
                self._set_offline_state(str(exc))

            elapsed = time.time() - loop_start
            sleep_time = max(0.05, self.config.poll_interval_sec - elapsed)
            self._stop_event.wait(sleep_time)

    def poll_once(self) -> BmsState:
        """Read BMS once and update latest state. Useful for unit/standalone tests too."""
        try:
            with self._modbus_lock:
                payload = self.driver.read_all()

            payload["asset_id"] = self.config.asset_id
            payload["timestamp"] = utc_now_iso()
            payload["last_success_ts"] = self.driver.last_success_ts

            new_state = BmsState.from_driver_payload(
                payload,
                gateway_id=self.config.gateway_id,
                keep_raw=False,
            )
            new_state.communication_status = "online"

            with self._lock:
                previous_online = self.latest_state.is_online()
                previous_alarms = set(self.latest_state.active_alarms)
                self.latest_state = new_state

            if not previous_online:
                self._log_event(
                    event_type="communication_restored",
                    message="BMS Modbus TCP communication restored",
                    extra=new_state.to_event_context(),
                )
                if self.config.print_status:
                    print("[BMS] Communication restored")

            self._handle_alarm_transitions(previous_alarms, set(new_state.active_alarms), new_state)
            self._maybe_log_telemetry(new_state)
            return new_state

        except Exception as exc:
            offline = self._set_offline_state(str(exc))
            self._maybe_log_telemetry(offline)
            return offline

    def _set_offline_state(self, message: str) -> BmsState:
        with self._lock:
            previous_online = self.latest_state.is_online()
            offline = BmsState.offline(
                message=message,
                gateway_id=self.config.gateway_id,
                asset_id=self.config.asset_id,
                last_success_ts=self.driver.last_success_ts,
            )
            self.latest_state = offline

        if previous_online:
            self._log_event(
                event_type="communication_lost",
                message=f"BMS Modbus TCP communication lost: {message}",
                extra=offline.to_event_context(),
            )
            if self.config.print_status:
                print(f"[BMS] Communication lost: {message}")
        return offline

    # ------------------------------------------------------------------
    # State accessors for UDP, TCP server, logging and Flutter API
    # ------------------------------------------------------------------
    def get_latest_state(self) -> BmsState:
        with self._lock:
            return self.latest_state

    def get_latest_state_dict(self) -> Dict[str, Any]:
        with self._lock:
            return self.latest_state.to_dict()

    def get_telemetry_payload(self) -> Dict[str, Any]:
        with self._lock:
            return self.latest_state.to_telemetry_dict()

    def get_alarm_payload(self) -> Dict[str, Any]:
        with self._lock:
            state = self.latest_state
            return {
                "status": "ok",
                "gateway_id": state.gateway_id,
                "asset_id": state.asset_id,
                "timestamp": state.timestamp,
                "communication_status": state.communication_status,
                "active_alarms": list(state.active_alarms),
                "alarm_count": state.alarm_count,
                "last_error": state.last_error,
            }

    def read_all_now(self) -> Dict[str, Any]:
        """Force an immediate Modbus read and return full state dictionary."""
        state = self.poll_once()
        return {
            "status": "ok" if state.is_online() else "error",
            "asset_id": self.config.asset_id,
            "data": state.to_dict(),
            "message": "BMS read completed" if state.is_online() else state.last_error,
        }

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------
    def execute_command(self, command: str, **kwargs: Any) -> Dict[str, Any]:
        """Execute a BMS command from TCP command server / Flutter API."""
        normalized = (command or "").strip().upper()

        read_commands = {"READ_BMS_ALL", "READ_BMS", "BMS_READ_ALL"}
        alarm_commands = {"READ_BMS_ALARMS", "BMS_READ_ALARMS"}

        if normalized in read_commands:
            return self.read_all_now()
        if normalized in alarm_commands:
            return self.get_alarm_payload()

        try:
            with self._modbus_lock:
                result = self.driver.execute_command(normalized)

            result.setdefault("asset_id", self.config.asset_id)

            if result.get("status") == "ok":
                self._log_event(
                    event_type="command_success",
                    message=f"BMS command success: {normalized}",
                    command=normalized,
                    extra=result,
                )
                # Small delay, then update state to reflect command/status changes from ModSim/BCU.
                if self.config.command_verify_delay_sec > 0:
                    time.sleep(self.config.command_verify_delay_sec)
                self.poll_once()
            else:
                self._log_event(
                    event_type="command_failed",
                    message=f"BMS command failed: {normalized} - {result.get('message')}",
                    command=normalized,
                    extra=result,
                )
            return result
        except Exception as exc:
            error = {
                "status": "error",
                "asset_id": self.config.asset_id,
                "command": normalized,
                "message": str(exc),
            }
            self._log_event(
                event_type="command_failed",
                message=f"BMS command failed: {normalized} - {exc}",
                command=normalized,
                extra=error,
            )
            return error

    # Convenience wrappers if other code wants direct methods.
    def start_precharge(self) -> Dict[str, Any]:
        return self.execute_command("START_BMS_PRECHARGE")

    def stop_precharge(self) -> Dict[str, Any]:
        return self.execute_command("STOP_BMS_PRECHARGE")

    def start_insulation_test(self) -> Dict[str, Any]:
        return self.execute_command("START_BMS_INSULATION_TEST")

    def reset_bcu(self) -> Dict[str, Any]:
        return self.execute_command("RESET_BCU")

    def fan_auto(self) -> Dict[str, Any]:
        return self.execute_command("BMS_FAN_AUTO")

    def fan_on(self) -> Dict[str, Any]:
        return self.execute_command("BMS_FAN_ON")

    def fan_off(self) -> Dict[str, Any]:
        return self.execute_command("BMS_FAN_OFF")

    # ------------------------------------------------------------------
    # Alarm/event/telemetry logging helpers
    # ------------------------------------------------------------------
    def _handle_alarm_transitions(self, previous: Set[str], current: Set[str], state: BmsState) -> None:
        raised = sorted(current - previous)
        cleared = sorted(previous - current)

        for alarm in raised:
            self._log_event(
                event_type="alarm_raised",
                message=f"BMS alarm raised: {alarm}",
                extra={**state.to_event_context(), "alarm": alarm},
            )
            if self.config.print_status:
                print(f"[BMS] Alarm raised: {alarm}")

        for alarm in cleared:
            self._log_event(
                event_type="alarm_cleared",
                message=f"BMS alarm cleared: {alarm}",
                extra={**state.to_event_context(), "alarm": alarm},
            )
            if self.config.print_status:
                print(f"[BMS] Alarm cleared: {alarm}")

    def _maybe_log_telemetry(self, state: BmsState) -> None:
        if not self.config.enable_storage_logging:
            return
        now = time.time()
        if now - self._last_log_ts < self.config.telemetry_log_interval_sec:
            return
        self._last_log_ts = now
        self._log_telemetry(state)

    def _log_telemetry(self, state: BmsState) -> None:
        if self.storage_logger is None:
            return
        row = state.to_log_row()

        # Support multiple logger method names to fit existing gateway code.
        try:
            if hasattr(self.storage_logger, "log_telemetry"):
                self.storage_logger.log_telemetry(self.config.asset_id, row)
            elif hasattr(self.storage_logger, "write_telemetry"):
                self.storage_logger.write_telemetry(self.config.asset_id, row)
            elif hasattr(self.storage_logger, "append_telemetry"):
                self.storage_logger.append_telemetry(self.config.asset_id, row)
            elif hasattr(self.storage_logger, "log_asset_telemetry"):
                self.storage_logger.log_asset_telemetry(self.config.asset_id, row, fields=BMS_LOG_FIELDS)
        except Exception as exc:
            if self.config.print_status:
                print(f"[BMS] Telemetry log error: {exc}")

    def _log_event(
        self,
        event_type: str,
        message: str,
        command: Optional[str] = None,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> None:
        if self.storage_logger is None:
            return

        event = {
            "timestamp": utc_now_iso(),
            "gateway_id": self.config.gateway_id,
            "asset_id": self.config.asset_id,
            "event_type": event_type,
            "command": command,
            "message": message,
        }
        if extra:
            for key, value in extra.items():
                if key not in event:
                    event[key] = value

        try:
            if hasattr(self.storage_logger, "log_event"):
                self.storage_logger.log_event(self.config.asset_id, event)
            elif hasattr(self.storage_logger, "write_event"):
                self.storage_logger.write_event(self.config.asset_id, event)
            elif hasattr(self.storage_logger, "append_event"):
                self.storage_logger.append_event(self.config.asset_id, event)
            elif hasattr(self.storage_logger, "log_asset_event"):
                self.storage_logger.log_asset_event(self.config.asset_id, event)
        except Exception as exc:
            if self.config.print_status:
                print(f"[BMS] Event log error: {exc}")


# -----------------------------------------------------------------------------
# Standalone service smoke test
# -----------------------------------------------------------------------------
def _main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Standalone BMS Gateway Service smoke test")
    parser.add_argument("--host", default=BMS_DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=BMS_DEFAULT_PORT)
    parser.add_argument("--unit-id", type=int, default=BMS_DEFAULT_UNIT_ID)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--address-offset", type=int, default=0)
    parser.add_argument("--once", action="store_true", help="Poll once and print state")
    parser.add_argument("--seconds", type=float, default=10.0, help="Run service for N seconds")
    parser.add_argument("--command", default="", help="Optional BMS command to execute")
    args = parser.parse_args()

    service = BmsGatewayService(
        BmsServiceConfig(
            host=args.host,
            port=args.port,
            unit_id=args.unit_id,
            timeout=args.timeout,
            address_offset=args.address_offset,
            print_status=True,
            enable_storage_logging=False,
        )
    )

    if args.once:
        state = service.poll_once()
        print(json.dumps(state.to_dict(), indent=2, default=str))
        return 0 if state.is_online() else 1

    service.start()
    try:
        if args.command:
            result = service.execute_command(args.command)
            print(json.dumps(result, indent=2, default=str))

        end = time.time() + max(1.0, args.seconds)
        while time.time() < end:
            time.sleep(1.0)
            print(json.dumps(service.get_telemetry_payload(), indent=2, default=str))
        return 0
    finally:
        service.stop()


if __name__ == "__main__":
    raise SystemExit(_main())
