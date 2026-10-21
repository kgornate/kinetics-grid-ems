from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from app.assets.bms_driver import BmsModbusDriver
from app.assets.pcs_driver import PcsModbusDriver
from app.core.config import ControlPairConfig, ControlSequenceConfig, GatewayConfig
from app.storage.sqlite_store import SQLiteStore

LOGGER = logging.getLogger(__name__)
Direction = Literal["charge", "discharge"]


class ControlStatusBusyError(RuntimeError):
    """Raised when an engineering live refresh cannot start immediately."""


class _FairRefreshLane:
    """One-at-a-time FIFO lane for expensive multi-device live refreshes.

    Modbus RTU traffic must remain serialized, but serialization must not allow
    a newly starting pair to repeatedly jump ahead of monitors that are already
    waiting. Each blocking caller receives a FIFO ticket. Non-blocking
    engineering reads never jump the queue.
    """

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._queue: deque[object] = deque()
        self._active = False

    def acquire(
        self,
        blocking: bool = True,
        timeout: float | None = None,
    ) -> bool:
        with self._condition:
            if not blocking:
                if self._active or self._queue:
                    return False
                self._active = True
                return True

            ticket = object()
            self._queue.append(ticket)
            deadline = (
                None
                if timeout is None
                else time.monotonic() + max(0.0, float(timeout))
            )

            while self._active or self._queue[0] is not ticket:
                if deadline is None:
                    self._condition.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._queue.remove(ticket)
                    self._condition.notify_all()
                    return False
                self._condition.wait(remaining)

            head = self._queue.popleft()
            if head is not ticket:
                raise RuntimeError("Refresh-lane FIFO corruption")
            self._active = True
            return True

    def release(self) -> None:
        with self._condition:
            if not self._active:
                raise RuntimeError("Cannot release an inactive refresh lane")
            self._active = False
            self._condition.notify_all()

    def diagnostics(self) -> dict[str, Any]:
        with self._condition:
            return {
                "policy": "fifo_single_flight",
                "active": self._active,
                "pending_count": len(self._queue),
            }


LIVE_STATUS_WAIT_TIMEOUT_SECONDS = 120.0
LIVE_STATUS_STALE_AFTER_SECONDS = 30.0


PCS_STOPPED_STATE = 0x0001
PCS_SOFT_START_STATE = 0x0002
PCS_SELF_TEST_STATE = 0x0004
PCS_STANDBY_STATE = 0x0008
PCS_RUNNING_STATE_BIT = 0x0010
PCS_ENERGY_SAVING_STATE_BIT = 0x0020
PCS_GRID_CONNECTED_STATE_BIT = 0x0040
PCS_FAULT_SHUTDOWN_BIT = 0x0400
PCS_PRECHARGE_PREP_ALLOWED_STATES = {
    PCS_STOPPED_STATE,
    PCS_SOFT_START_STATE,
    PCS_SELF_TEST_STATE,
    PCS_STANDBY_STATE,
}
PCS_PRECHARGE_PREP_MAX_DEENERGIZED_V = 50.0
PCS_START_VALUE = 0xFF00
PCS_STOP_VALUE = 0x00FF
PCS_REMOTE_VALUE = 0x00FF
PCS_PQ_PRODUCT_MODE = 1
PCS_CONSTANT_POWER_MODE = 0

BMS_RECOVERY_IDLE_VALUE = 0
BMS_RECOVERY_TRIGGER_VALUE = 1
PCS_ZERO_SETPOINT_TOLERANCE_KW = 0.11
PCS_ZERO_ACTUAL_POWER_TOLERANCE_KW = 1.0
BMS_INSULATION_START_VALUE = 1
BMS_INSULATION_MIN_RETRIGGER_SECONDS = 3.0



def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BmsPcsControlService:
    """Field-validated BMS-to-PCS sequence controller.

    The same service supports guarded commissioning steps and an optional
    automatic sequence. Automatic execution remains protected by independent
    configuration, write gates and a dedicated confirmation phrase.
    """

    def __init__(
        self,
        gateway_config: GatewayConfig,
        bms_driver: BmsModbusDriver,
        pcs_driver: PcsModbusDriver,
        store: SQLiteStore,
        snapshot_provider: Callable[[int, str], dict[str, Any]] | None = None,
    ) -> None:
        self.gateway_config = gateway_config
        self.config: ControlSequenceConfig = gateway_config.control_sequence
        self.bms_driver = bms_driver
        self.pcs_driver = pcs_driver
        self.store = store
        self._snapshot_provider = snapshot_provider
        self._lock = threading.RLock()
        self._sequence_threads: dict[str, threading.Thread] = {}
        self._abort_events: dict[str, threading.Event] = {
            pair.pair_id: threading.Event() for pair in self.config.pairs
        }
        self._monitor_threads: dict[str, threading.Thread] = {}
        self._monitor_stop_events: dict[str, threading.Event] = {
            pair.pair_id: threading.Event() for pair in self.config.pairs
        }
        self._safe_stop_locks: dict[str, threading.RLock] = {
            pair.pair_id: threading.RLock() for pair in self.config.pairs
        }
        self._runtime_monitor_stats: dict[str, dict[str, Any]] = {
            pair.pair_id: {
                "samples": 0,
                "cache_samples": 0,
                "live_fallbacks": 0,
                "cache_quality_failures": 0,
                "deferred_verifications": 0,
                "verification_recoveries": 0,
                "consecutive_unverified_samples": 0,
                "unverified_since": None,
                "last_verified_at": None,
                "last_deferred_reason": None,
                "safety_stops": 0,
                "last_sample_at": None,
                "last_source": None,
                "last_cache_ages_seconds": {},
                "last_errors": [],
                "last_violations": [],
            }
            for pair in self.config.pairs
        }

        # Live control-status reads are expensive: one request performs many BMS
        # and PCS transactions.  Keep exactly one live refresh per pair and one
        # live refresh globally so HTTP polling cannot create an unbounded queue
        # of Modbus work. Internal control operations may wait for the bounded
        # lane; public engineering requests use non-blocking single-flight mode.
        self._status_refresh_locks: dict[str, threading.Lock] = {
            pair.pair_id: threading.Lock() for pair in self.config.pairs
        }
        self._status_refresh_global = _FairRefreshLane()
        self._last_live_status: dict[str, dict[str, Any]] = {}
        self._status_refresh_stats: dict[str, dict[str, Any]] = {
            pair.pair_id: {
                "active": False,
                "started": 0,
                "completed": 0,
                "failed": 0,
                "busy_responses": 0,
                "last_started_at": None,
                "last_completed_at": None,
                "last_duration_ms": None,
                "last_error": None,
            }
            for pair in self.config.pairs
        }

        self._runtime: dict[str, dict[str, Any]] = {
            pair.pair_id: {
                "pair_id": pair.pair_id,
                "stage": "idle",
                "last_action": None,
                "last_error": None,
                "last_updated_at": now_iso(),
                "requested_direction": None,
                "requested_power_kw": 0.0,
                "commanded_power_kw": 0.0,
                "run_id": None,
                "run_mode": None,
                "run_status": "idle",
                "started_at": None,
                "completed_at": None,
                "steps": [],
                "monitor_active": False,
            }
            for pair in self.config.pairs
        }

    def _pair(self, pair_id: str) -> ControlPairConfig:
        pair = next((item for item in self.config.pairs if item.pair_id == pair_id), None)
        if pair is None:
            raise KeyError(f"Unknown control pair: {pair_id}")
        if not pair.enabled:
            raise PermissionError(f"Control pair {pair_id} is disabled")
        if pair.rack_id not in {rack.rack_id for rack in self.gateway_config.bms.racks}:
            raise KeyError(f"BMS rack {pair.rack_id} is not configured")
        if pair.pcs_asset_id not in {device.asset_id for device in self.gateway_config.pcs.devices}:
            raise KeyError(f"PCS asset {pair.pcs_asset_id} is not configured")
        return pair

    def _require_confirmation(self, confirmation: str) -> None:
        if confirmation != self.config.confirmation_phrase:
            raise PermissionError(
                f"Hardware write confirmation must equal {self.config.confirmation_phrase!r}"
            )

    def _require_write_gates(self, confirmation: str) -> None:
        self._require_confirmation(confirmation)
        if not self.config.enabled:
            raise PermissionError("Staged BMS/PCS control is disabled in configuration")
        if self.gateway_config.mode != "control_enabled":
            raise PermissionError("Gateway mode must be control_enabled for staged writes")
        if not self.gateway_config.bms.write_enabled:
            raise PermissionError("BMS writes are disabled")
        if not self.gateway_config.pcs.write_enabled:
            raise PermissionError("PCS writes are disabled")

    def _update_runtime(self, pair_id: str, **changes: Any) -> None:
        with self._lock:
            runtime = self._runtime[pair_id]
            runtime.update(changes)
            runtime["last_updated_at"] = now_iso()

    def _runtime_snapshot(self, pair_id: str) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._runtime[pair_id])

    @staticmethod
    def _acquire_refresh_gate(
        gate: Any,
        *,
        wait: bool,
        timeout_seconds: float | None = None,
    ) -> bool:
        if not wait:
            return gate.acquire(blocking=False)
        timeout = (
            LIVE_STATUS_WAIT_TIMEOUT_SECONDS
            if timeout_seconds is None
            else max(0.0, float(timeout_seconds))
        )
        return gate.acquire(timeout=timeout)

    def _busy_live_status(
        self,
        pair_id: str,
        *,
        reason: str,
        return_cached_if_busy: bool,
    ) -> dict[str, Any]:
        with self._lock:
            stats = self._status_refresh_stats[pair_id]
            stats["busy_responses"] += 1
            cached = deepcopy(self._last_live_status.get(pair_id))

        if return_cached_if_busy and cached is not None:
            completed_at = cached.get("refresh", {}).get("completed_at")
            age_seconds = None
            if completed_at:
                try:
                    age_seconds = max(
                        0.0,
                        (
                            datetime.now(timezone.utc)
                            - datetime.fromisoformat(str(completed_at))
                        ).total_seconds(),
                    )
                except (TypeError, ValueError):
                    age_seconds = None
            cached["runtime"] = self._runtime_snapshot(pair_id)
            cached["refresh"] = {
                **cached.get("refresh", {}),
                "requested_fresh": True,
                "source": "cached_while_live_refresh_busy",
                "busy": True,
                "busy_reason": reason,
                "cache_age_seconds": (
                    None if age_seconds is None else round(age_seconds, 3)
                ),
                "stale": (
                    True
                    if age_seconds is None
                    else age_seconds > LIVE_STATUS_STALE_AFTER_SECONDS
                ),
            }
            return cached

        raise ControlStatusBusyError(
            f"Live status refresh is already busy for {pair_id} ({reason}). "
            "Use fresh=false for normal polling and retry the engineering "
            "fresh=true request later."
        )

    def refresh_diagnostics(self) -> dict[str, Any]:
        with self._lock:
            pairs = deepcopy(self._status_refresh_stats)
            cached_pairs = sorted(self._last_live_status)
        for pair_id, values in pairs.items():
            values["pair_gate_locked"] = self._status_refresh_locks[pair_id].locked()
            values["has_cached_live_status"] = pair_id in cached_pairs
        global_lane = self._status_refresh_global.diagnostics()
        return {
            "mode": "fifo_single_flight",
            "normal_status_default": "cached_runtime",
            "global_live_refresh_limit": 1,
            "global_live_refresh_policy": "fifo",
            "internal_wait_timeout_seconds": LIVE_STATUS_WAIT_TIMEOUT_SECONDS,
            "cached_busy_stale_after_seconds": LIVE_STATUS_STALE_AFTER_SECONDS,
            "global_active": global_lane["active"],
            "global_pending_count": global_lane["pending_count"],
            "global_lane": global_lane,
            "pairs": pairs,
        }

    def _audit(
        self,
        username: str,
        pair: ControlPairConfig,
        stage: str,
        request: Any,
        response: dict[str, Any],
        status: str = "success",
    ) -> None:
        self.store.audit_command(
            username,
            f"{pair.pair_id}:{pair.pcs_asset_id}:bms_rack_{pair.rack_id}",
            f"control_sequence.{stage}",
            request,
            status,
            response,
        )
        self.store.event(
            "control_sequence",
            f"Control stage {stage} {status}",
            asset_id=pair.pcs_asset_id,
            payload={"pair_id": pair.pair_id, **response},
        )

    @staticmethod
    def _value(point: dict[str, Any] | None) -> float | int | None:
        if not point:
            return None
        return point.get("value")

    def _read_safely(self, target: str, function: Any, *args: Any) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
        try:
            return function(*args), None
        except Exception as error:
            return None, {"target": target, "error": str(error)}

    @staticmethod
    def _pcs_ready_state(raw_state: int | float | None) -> bool:
        if raw_state is None:
            return False
        raw = int(raw_state)
        if raw & PCS_FAULT_SHUTDOWN_BIT:
            return False
        return bool(
            raw
            & (
                PCS_STANDBY_STATE
                | PCS_RUNNING_STATE_BIT
                | PCS_ENERGY_SAVING_STATE_BIT
                | PCS_GRID_CONNECTED_STATE_BIT
            )
        )

    def _voltages_match(self, first: Any, second: Any) -> bool:
        if first is None or second is None:
            return False
        return abs(float(first) - float(second)) <= self.config.ready_voltage_match_tolerance_v

    @staticmethod
    def _iso_age_seconds(value: Any) -> float | None:
        if not value:
            return None
        try:
            stamp = datetime.fromisoformat(str(value))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds())
        except (TypeError, ValueError):
            return None

    def _poll_quality(
        self,
        asset: dict[str, Any],
        poll_class: str,
        *,
        label: str,
        max_age_seconds: float,
    ) -> tuple[dict[str, Any], list[dict[str, str]]]:
        errors: list[dict[str, str]] = []
        status = (asset or {}).get("poll_status", {}).get(poll_class, {})
        timestamp = status.get("timestamp")
        age = self._iso_age_seconds(timestamp)
        read_errors = status.get("read_errors") or []
        online = bool(status.get("online", (asset or {}).get("online", False)))
        if not status:
            errors.append({"target": label, "error": f"missing_{poll_class}_poll_status"})
        elif not online:
            errors.append({"target": label, "error": f"{poll_class}_poll_offline"})
        elif read_errors:
            errors.append({"target": label, "error": f"{poll_class}_poll_read_error: {read_errors}"})
        elif age is None:
            errors.append({"target": label, "error": f"invalid_{poll_class}_poll_timestamp"})
        elif age > max_age_seconds:
            errors.append(
                {
                    "target": label,
                    "error": (
                        f"stale_{poll_class}_poll age={age:.3f}s "
                        f"limit={max_age_seconds:.3f}s"
                    ),
                }
            )
        return {
            "timestamp": timestamp,
            "age_seconds": None if age is None else round(age, 3),
            "max_age_seconds": round(max_age_seconds, 3),
            "online": online,
            "read_errors": deepcopy(read_errors),
            "fresh": not errors,
        }, errors

    @staticmethod
    def _cached_point(
        asset: dict[str, Any],
        key: str,
        *,
        target: str,
        required: bool,
        errors: list[dict[str, str]],
    ) -> dict[str, Any] | None:
        point = (asset or {}).get("telemetry", {}).get(key)
        if point is None and required:
            errors.append({"target": target, "error": f"missing_cached_point:{key}"})
        return deepcopy(point) if point is not None else None

    def _build_status_from_reads(
        self,
        pair_id: str,
        pair: ControlPairConfig,
        reads: dict[str, dict[str, Any] | None],
        errors: list[dict[str, str]],
        *,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        rack_voltage = self._value(reads["rack_voltage"])
        charge_limit = self._value(reads["rack_charge_limit"])
        discharge_limit = self._value(reads["rack_discharge_limit"])
        pcs_dc_bus = self._value(reads["pcs_dc_bus_voltage"])
        pcs_state = self._value(reads["pcs_operating_state"])
        pcs_battery_voltage = self._value(reads["pcs_battery_voltage"])
        pcs_status_word_1 = self._value(reads["pcs_status_word_1"])
        pcs_status_word_2 = self._value(reads["pcs_status_word_2"])
        pcs_input_fault_word = self._value(reads["pcs_input_fault_word"])
        pcs_system_fault_ext3 = self._value(reads["pcs_system_fault_ext3"])

        pcs_status_word_1_raw = None if pcs_status_word_1 is None else int(pcs_status_word_1)
        pcs_status_word_2_raw = None if pcs_status_word_2 is None else int(pcs_status_word_2)
        pcs_input_fault_word_raw = None if pcs_input_fault_word is None else int(pcs_input_fault_word)
        pcs_system_fault_ext3_raw = None if pcs_system_fault_ext3 is None else int(pcs_system_fault_ext3)

        pcs_remote_feedback = (
            None if pcs_status_word_1_raw is None else bool(pcs_status_word_1_raw & (1 << 0))
        )
        pcs_authorized = (
            None if pcs_status_word_1_raw is None else bool(pcs_status_word_1_raw & (1 << 1))
        )
        pcs_dc_breaker_open = (
            None if pcs_status_word_2_raw is None else bool(pcs_status_word_2_raw & (1 << 6))
        )
        pcs_dc_breaker_feedback_closed = (
            None if pcs_input_fault_word_raw is None else bool(pcs_input_fault_word_raw & (1 << 7))
        )
        pcs_dc_soft_start_fault = (
            None if pcs_system_fault_ext3_raw is None else bool(pcs_system_fault_ext3_raw & (1 << 2))
        )
        pcs_dc_soft_start_relay_fault = (
            None if pcs_system_fault_ext3_raw is None else bool(pcs_system_fault_ext3_raw & (1 << 3))
        )
        enable_raw = self._value(reads["bank_rack_enable_state"])
        enable_bit = None
        if enable_raw is not None and 1 <= pair.rack_id <= 16:
            enable_bit = (int(enable_raw) >> (pair.rack_id - 1)) & 1
        contactor_bits = (reads["contactor_state"] or {}).get("bitfields", {})
        positive_closed = contactor_bits.get("positive_contactor_state") == 1
        negative_closed = contactor_bits.get("negitive_contactor_state") == 1
        contactors_ready = (
            positive_closed and negative_closed
            if self.config.require_positive_and_negative_contactors
            else positive_closed or negative_closed
        )
        precharge_ok = self._value(reads["precharge_state"]) == 3
        bms_charge_power_limit_kw = None
        bms_discharge_power_limit_kw = None
        if rack_voltage is not None and charge_limit is not None:
            bms_charge_power_limit_kw = abs(float(rack_voltage) * float(charge_limit) / 1000.0)
        if rack_voltage is not None and discharge_limit is not None:
            bms_discharge_power_limit_kw = abs(float(rack_voltage) * float(discharge_limit) / 1000.0)

        bank_fault_bits = (reads["bank_external_fault"] or {}).get("bitfields", {})
        detailed_fault_points = {
            "bank_level1_alarm_1": reads.get("bank_level1_alarm_1"),
            "bank_level1_alarm_2": reads.get("bank_level1_alarm_2"),
            "bank_rack_fault": reads.get("bank_rack_fault"),
            "bank_fault_summary_2": reads.get("bank_fault_summary_2"),
            "rack_external_fault": reads.get("rack_external_fault"),
            "rack_critical_1": reads.get("rack_critical_1"),
            "rack_critical_2": reads.get("rack_critical_2"),
        }
        detailed_fault_raw = {
            key: int((point or {}).get("raw") or 0)
            for key, point in detailed_fault_points.items()
        }
        documented_critical_fault = any(value != 0 for value in detailed_fault_raw.values())
        summary_system_fault_bit = bank_fault_bits.get("system_fault") == 1

        global_system_full_summary = bank_fault_bits.get("system_full") == 1
        global_system_empty_summary = bank_fault_bits.get("system_empty") == 1
        rack_charge_limit_available = (
            charge_limit is not None
            and float(charge_limit) >= self.config.minimum_bms_current_limit_a
        )
        rack_discharge_limit_available = (
            discharge_limit is not None
            and float(discharge_limit) >= self.config.minimum_bms_current_limit_a
        )

        blockers = {
            "emergency_stop_fault": bank_fault_bits.get("emergency_stop_fault") == 1,
            "system_fault": documented_critical_fault,
            "documented_critical_fault": documented_critical_fault,
            "summary_system_fault_bit": summary_system_fault_bit,
            "detailed_fault_raw": detailed_fault_raw,
            "system_charge_prohibited": documented_critical_fault or not rack_charge_limit_available,
            "system_discharge_prohibited": documented_critical_fault or not rack_discharge_limit_available,
            "global_summary_system_full": global_system_full_summary,
            "global_summary_system_empty": global_system_empty_summary,
            "global_summary_direction_bits_contradictory": (
                global_system_full_summary and global_system_empty_summary
            ),
            "direction_permission_source": "selected_rack_current_limits_and_detailed_faults",
            "pcs_control_fault": bank_fault_bits.get("pcs_ctrl") == 1,
        }

        result = {
            "pair": pair.model_dump(),
            "timestamp": timestamp or now_iso(),
            "runtime": self._runtime_snapshot(pair_id),
            "write_gates": {
                "control_sequence_enabled": self.config.enabled,
                "gateway_mode": self.gateway_config.mode,
                "bms_write_enabled": self.gateway_config.bms.write_enabled,
                "pcs_write_enabled": self.gateway_config.pcs.write_enabled,
                "full_automatic_sequence_allowed": self.config.allow_full_automatic_sequence,
            },
            "summary": {
                "rack_enabled": 1 if (precharge_ok and contactors_ready) else 0,
                "rack_runtime_ready": precharge_ok and contactors_ready,
                "bau_rack_enable_feedback": enable_bit,
                "rack_run_state": self._value(reads.get("rack_run_state")),
                "rack_voltage_v": rack_voltage,
                "rack_voltage_valid": (
                    rack_voltage is not None
                    and self.config.bms_rack_voltage_min_v <= float(rack_voltage) <= self.config.bms_rack_voltage_max_v
                ),
                "insulation_command": self._value(reads["insulation_command"]),
                "insulation_resistance_kohm": self._value(reads["insulation_resistance"]),
                "insulation_resistance_pos_kohm": self._value(reads["insulation_resistance_pos"]),
                "insulation_resistance_neg_kohm": self._value(reads["insulation_resistance_neg"]),
                "precharge_state": self._value(reads["precharge_state"]),
                "precharge_command": self._value(reads["precharge_command"]),
                "precharge_success": precharge_ok,
                "positive_contactor_closed": positive_closed,
                "negative_contactor_closed": negative_closed,
                "contactors_ready": contactors_ready,
                "pcs_dc_bus_voltage_v": pcs_dc_bus,
                "pcs_battery_voltage_v": pcs_battery_voltage,
                "pcs_status_word_1_raw": pcs_status_word_1_raw,
                "pcs_remote_feedback": pcs_remote_feedback,
                "pcs_authorized": pcs_authorized,
                "pcs_status_word_2_raw": pcs_status_word_2_raw,
                "pcs_dc_breaker_open": pcs_dc_breaker_open,
                "pcs_dc_breaker_feedback_closed": pcs_dc_breaker_feedback_closed,
                "pcs_dc_soft_start_fault": pcs_dc_soft_start_fault,
                "pcs_dc_soft_start_relay_fault": pcs_dc_soft_start_relay_fault,
                "pcs_dc_bus_valid": (
                    pcs_dc_bus is not None
                    and self.config.pcs_dc_bus_voltage_min_v <= float(pcs_dc_bus) <= self.config.pcs_dc_bus_voltage_max_v
                ),
                "pcs_operating_state": pcs_state,
                "pcs_fault_shutdown": pcs_state is not None and bool(int(pcs_state) & PCS_FAULT_SHUTDOWN_BIT),
                "pcs_actual_power_kw": self._value(reads["pcs_actual_power"]),
                "pcs_power_setpoint_kw": self._value(reads["pcs_power_setpoint"]),
                "rack_charge_current_limit_a": charge_limit,
                "rack_discharge_current_limit_a": discharge_limit,
                "bms_charge_power_limit_kw": bms_charge_power_limit_kw,
                "bms_discharge_power_limit_kw": bms_discharge_power_limit_kw,
                "blockers": blockers,
            },
            "points": reads,
            "errors": errors,
        }
        result["workflow"] = self._workflow_from_summary(
            result["summary"], result["runtime"]
        )
        return result

    def _read_cached_runtime_status(
        self,
        pair_id: str,
        pair: ControlPairConfig,
    ) -> dict[str, Any]:
        if self._snapshot_provider is None:
            raise RuntimeError("Runtime monitor snapshot provider is unavailable")
        snapshot = self._snapshot_provider(pair.rack_id, pair.pcs_asset_id)
        bank = snapshot.get("bank") or {}
        rack = snapshot.get("rack") or {}
        pcs = snapshot.get("pcs") or {}
        errors: list[dict[str, str]] = []

        fast_limit = max(3.0, float(self.gateway_config.bms.poll_fast_seconds) * 3.0)
        normal_limit = max(15.0, float(self.gateway_config.bms.poll_normal_seconds) * 3.0)
        pcs_limit = max(15.0, float(self.gateway_config.pcs.poll_seconds) * 3.0)
        freshness: dict[str, dict[str, Any]] = {}
        for key, asset, poll_class, label, limit in (
            ("bank_fast", bank, "fast", "bms_bank", fast_limit),
            ("rack_fast", rack, "fast", f"bms_rack_{pair.rack_id}", fast_limit),
            ("rack_normal", rack, "normal", f"bms_rack_{pair.rack_id}", normal_limit),
            ("pcs", pcs, "pcs", pair.pcs_asset_id, pcs_limit),
        ):
            quality, quality_errors = self._poll_quality(
                asset,
                poll_class,
                label=label,
                max_age_seconds=limit,
            )
            freshness[key] = quality
            errors.extend(quality_errors)

        def cached(
            asset: dict[str, Any],
            key: str,
            target: str,
            *,
            required: bool = True,
        ) -> dict[str, Any] | None:
            return self._cached_point(
                asset,
                key,
                target=target,
                required=required,
                errors=errors,
            )

        reads: dict[str, dict[str, Any] | None] = {
            "bank_external_fault": cached(bank, "external_fault_state", "bank_external_fault"),
            "bank_level1_alarm_1": cached(bank, "external_level1_alarm", "bank_level1_alarm_1"),
            "bank_level1_alarm_2": cached(bank, "bcu_external_lv1_alm_sum_ii", "bank_level1_alarm_2"),
            "bank_rack_fault": cached(bank, "rack_fault", "bank_rack_fault"),
            "bank_fault_summary_2": cached(bank, "fault_info_sum2", "bank_fault_summary_2"),
            "bank_rack_enable_state": cached(bank, "rack_enable_state_l16", "bank_rack_enable_state", required=False),
            "rack_external_fault": cached(rack, "bcu_external_fault_alarm", "rack_external_fault"),
            "rack_critical_1": cached(rack, "external_critical", "rack_critical_1"),
            "rack_critical_2": cached(rack, "external_stop_alarm2", "rack_critical_2"),
            "rack_run_state": cached(rack, "bcu_run_state", "rack_run_state", required=False),
            "rack_voltage": cached(rack, "vrack", "rack_voltage"),
            "rack_charge_limit": cached(rack, "irack_chg_limit", "rack_charge_limit"),
            "rack_discharge_limit": cached(rack, "irack_dsg_limit", "rack_discharge_limit"),
            "insulation_command": cached(rack, "start_insulation_sampleing", "insulation_command", required=False),
            "insulation_resistance": cached(rack, "ir", "insulation_resistance", required=False),
            "insulation_resistance_pos": cached(rack, "ir_pos", "insulation_resistance_pos", required=False),
            "insulation_resistance_neg": cached(rack, "ir_neg", "insulation_resistance_neg", required=False),
            "precharge_state": cached(rack, "pre_charge_state", "precharge_state"),
            "precharge_command": cached(rack, "start_pre_chg_operate", "precharge_command", required=False),
            "contactor_state": cached(rack, "contactor_state", "contactor_state"),
            "pcs_dc_bus_voltage": cached(pcs, "dc_bus_voltage", "pcs_dc_bus_voltage"),
            "pcs_battery_voltage": cached(pcs, "battery_voltage", "pcs_battery_voltage"),
            "pcs_operating_state": cached(pcs, "operating_state", "pcs_operating_state"),
            "pcs_status_word_1": cached(pcs, "status_word_1", "pcs_status_word_1"),
            "pcs_status_word_2": cached(pcs, "status_word_2", "pcs_status_word_2"),
            "pcs_input_fault_word": cached(pcs, "reg_1210", "pcs_input_fault_word"),
            "pcs_system_fault_ext3": cached(pcs, "reg_121a", "pcs_system_fault_ext3"),
            "pcs_actual_power": cached(pcs, "grid_active_power", "pcs_actual_power"),
            "pcs_on_off_command": cached(pcs, "remote_on_off_command", "pcs_on_off_command", required=False),
            "pcs_remote_local_mode": cached(pcs, "remote_local_mode", "pcs_remote_local_mode", required=False),
            "pcs_product_mode": cached(pcs, "product_run_mode", "pcs_product_mode", required=False),
            "pcs_pq_mode": cached(pcs, "pq_work_mode", "pcs_pq_mode", required=False),
            "pcs_power_setpoint": cached(pcs, "active_power_setpoint", "pcs_power_setpoint"),
        }
        result = self._build_status_from_reads(
            pair_id,
            pair,
            reads,
            errors,
            timestamp=snapshot.get("timestamp"),
        )
        result["refresh"] = {
            "requested_fresh": False,
            "source": "background_poll_cache",
            "busy": False,
            "stale": bool(errors),
            "snapshot_sequence": snapshot.get("sequence"),
            "snapshot_timestamp": snapshot.get("timestamp"),
            "freshness": freshness,
        }
        return result

    def runtime_monitor_sample(self, pair_id: str) -> dict[str, Any]:
        pair = self._pair(pair_id)
        return self._read_cached_runtime_status(pair_id, pair)

    def all_pair_status(self) -> dict[str, Any]:
        """Return one cache-only control snapshot for every enabled pair.

        This endpoint is designed for Flutter/SCADA overview polling. It never
        performs direct hardware reads, so displaying all pair states cannot
        compete with automatic sequences or runtime safety monitoring.
        """
        statuses: list[dict[str, Any]] = []
        by_pair_id: dict[str, dict[str, Any]] = {}
        for pair in self.config.pairs:
            if not pair.enabled:
                continue
            status = self._read_cached_runtime_status(pair.pair_id, pair)
            statuses.append(status)
            by_pair_id[pair.pair_id] = status

        active_pairs = []
        starting_pairs = []
        failed_pairs = []
        for status in statuses:
            runtime = status.get("runtime", {})
            pair_id = status.get("pair", {}).get("pair_id")
            run_status = runtime.get("run_status")
            commanded = abs(float(runtime.get("commanded_power_kw") or 0.0))
            if run_status == "running":
                starting_pairs.append(pair_id)
            if commanded > PCS_ZERO_SETPOINT_TOLERANCE_KW:
                active_pairs.append(pair_id)
            if run_status in {"failed", "aborted"}:
                failed_pairs.append(pair_id)

        return {
            "timestamp": now_iso(),
            "source": "background_poll_cache",
            "count": len(statuses),
            "pairs": statuses,
            "by_pair_id": by_pair_id,
            "summary": {
                "active_pair_count": len(active_pairs),
                "active_pairs": active_pairs,
                "starting_pair_count": len(starting_pairs),
                "starting_pairs": starting_pairs,
                "failed_pair_count": len(failed_pairs),
                "failed_pairs": failed_pairs,
                "parallel_operation_supported": True,
            },
        }

    def runtime_monitor_diagnostics(self) -> dict[str, Any]:
        with self._lock:
            stats = deepcopy(self._runtime_monitor_stats)
            active = {
                pair_id: bool(thread and thread.is_alive())
                for pair_id, thread in self._monitor_threads.items()
            }
        return {
            "mode": "background_poll_cache_with_live_fallback",
            "bms_fast_poll_seconds": self.gateway_config.bms.poll_fast_seconds,
            "bms_normal_poll_seconds": self.gateway_config.bms.poll_normal_seconds,
            "pcs_poll_seconds": self.gateway_config.pcs.poll_seconds,
            "runtime_monitor_interval_seconds": self.config.runtime_monitor_interval_seconds,
            "runtime_monitor_refresh_wait_seconds": (
                self.config.runtime_monitor_refresh_wait_seconds
            ),
            "runtime_monitor_max_unverified_seconds": (
                self.config.runtime_monitor_max_unverified_seconds
            ),
            "contention_policy": (
                "FIFO live-refresh queue plus defer/retry until unverified timeout; "
                "do not safe-stop on global_refresh_lane_busy alone"
            ),
            "safe_stop_monitor_quiesce": True,
            "active_threads": active,
            "pairs": stats,
        }

    def _runtime_monitor_status(
        self,
        pair_id: str,
        pair: ControlPairConfig,
    ) -> dict[str, Any]:
        """Return a safety sample without treating scheduler contention as a fault.

        The background cache is preferred because it is cheap and already shared
        with the dashboard.  When the cache is stale/incomplete, the monitor asks
        for a bounded live confirmation and waits its turn on the global refresh
        lane.  A busy lane or transient live-read failure is reported as deferred
        verification; the worker applies a configurable grace window before any
        fail-safe stop.
        """
        cached = self._read_cached_runtime_status(pair_id, pair)
        if not cached.get("errors"):
            cached["runtime_verification"] = {
                "verified": True,
                "deferred": False,
                "source": "background_poll_cache",
                "verified_at": now_iso(),
            }
            return cached

        with self._lock:
            self._runtime_monitor_stats[pair_id]["cache_quality_failures"] += 1

        try:
            live = self.status(
                pair_id,
                fresh=True,
                wait_for_refresh=True,
                return_cached_if_busy=False,
                refresh_wait_timeout_seconds=(
                    self.config.runtime_monitor_refresh_wait_seconds
                ),
            )
        except ControlStatusBusyError as error:
            cached["refresh"] = {
                **cached.get("refresh", {}),
                "source": "runtime_verification_deferred",
                "busy": True,
                "busy_reason": "global_or_pair_refresh_lane_busy",
                "verification_deferred": True,
            }
            cached["runtime_verification"] = {
                "verified": False,
                "deferred": True,
                "reason": "refresh_lane_busy",
                "error": str(error),
                "requested_at": now_iso(),
            }
            return cached
        except Exception as error:
            LOGGER.warning(
                "Runtime live verification deferred pair=%s error=%s",
                pair_id,
                error,
            )
            cached["refresh"] = {
                **cached.get("refresh", {}),
                "source": "runtime_live_verification_failed",
                "busy": False,
                "verification_deferred": True,
            }
            cached["runtime_verification"] = {
                "verified": False,
                "deferred": True,
                "reason": "live_refresh_failed",
                "error": str(error),
                "requested_at": now_iso(),
            }
            return cached

        live["refresh"] = {
            **live.get("refresh", {}),
            "source": "live_hardware_fallback_for_cache_quality",
            "cache_errors": deepcopy(cached.get("errors", [])),
            "cache_freshness": deepcopy(
                cached.get("refresh", {}).get("freshness", {})
            ),
        }
        with self._lock:
            self._runtime_monitor_stats[pair_id]["live_fallbacks"] += 1

        if live.get("errors"):
            live["refresh"]["verification_deferred"] = True
            live["runtime_verification"] = {
                "verified": False,
                "deferred": True,
                "reason": "live_refresh_returned_read_errors",
                "errors": deepcopy(live.get("errors", [])),
                "requested_at": now_iso(),
            }
        else:
            live["runtime_verification"] = {
                "verified": True,
                "deferred": False,
                "source": "live_hardware_fallback_for_cache_quality",
                "verified_at": now_iso(),
            }
        return live

    def _workflow_from_summary(self, summary: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
        blockers = summary.get("blockers", {})
        state = summary.get("pcs_operating_state")
        pcs_configured = (
            summary.get("pcs_remote_feedback") is True
            and abs(float(summary.get("pcs_power_setpoint_kw") or 0.0)) <= PCS_ZERO_SETPOINT_TOLERANCE_KW
        )
        # Vendor/field finding (2026-07-28): individual rack runtime control is
        # performed through that rack BCU's 0x0402 precharge command. The BAU
        # 0x3005-0x3008 indexed rack-enable words are commissioning/debug data
        # and must not be used by the normal EMS sequence. Keep the BAU bit as
        # diagnostic data, but derive operational rack readiness locally.
        bau_rack_enabled = summary.get("bau_rack_enable_feedback") == 1
        precharge_complete = bool(summary.get("precharge_success")) and bool(summary.get("contactors_ready"))
        rack_runtime_ready = bool(summary.get("rack_runtime_ready", precharge_complete))
        input_energized = (
            bool(summary.get("rack_voltage_valid"))
            and self._voltages_match(summary.get("rack_voltage_v"), summary.get("pcs_battery_voltage_v"))
        )
        dc_ready = (
            bool(summary.get("pcs_dc_breaker_feedback_closed"))
            and bool(summary.get("pcs_dc_bus_valid"))
            and self._voltages_match(summary.get("pcs_dc_bus_voltage_v"), summary.get("pcs_battery_voltage_v"))
        )
        pcs_ready = (
            self._pcs_ready_state(state)
            and dc_ready
            and not bool(summary.get("pcs_fault_shutdown"))
            and not bool(summary.get("pcs_dc_soft_start_fault"))
            and not bool(summary.get("pcs_dc_soft_start_relay_fault"))
        )
        setpoint = float(summary.get("pcs_power_setpoint_kw") or 0.0)
        actual = float(summary.get("pcs_actual_power_kw") or 0.0)
        power_active = abs(setpoint) > PCS_ZERO_SETPOINT_TOLERANCE_KW
        stopped_safe = (
            int(summary.get("precharge_state") or 0) == 0
            and not bool(summary.get("positive_contactor_closed"))
            and not bool(summary.get("negative_contactor_closed"))
            and int(state or 0) == PCS_STOPPED_STATE
            and abs(setpoint) <= PCS_ZERO_SETPOINT_TOLERANCE_KW
            and abs(actual) <= PCS_ZERO_ACTUAL_POWER_TOLERANCE_KW
        )
        steps = [
            {"key": "pcs_configured", "label": "PCS configured at 0 kW", "complete": pcs_configured},
            {
                "key": "rack_enabled",
                "label": "Individual rack BCU precharged/connected",
                "complete": rack_runtime_ready,
                "diagnostic_bau_feedback": bau_rack_enabled,
            },
            {"key": "bms_precharge", "label": "BMS precharge and main contactors", "complete": precharge_complete},
            {"key": "pcs_input_energized", "label": "Battery voltage available at PCS input", "complete": input_energized},
            {"key": "pcs_dc_ready", "label": "PCS soft-start and DC breaker complete", "complete": dc_ready},
            {"key": "pcs_ready", "label": "PCS ready at zero power", "complete": pcs_ready},
            {"key": "power_active", "label": "Requested charge/discharge power active", "complete": power_active},
        ]
        if stopped_safe:
            system_state = "stopped_safe"
        elif power_active and setpoint < 0:
            system_state = "charging"
        elif power_active and setpoint > 0:
            system_state = "discharging"
        elif pcs_ready:
            system_state = "ready_zero_power"
        elif precharge_complete and input_energized:
            system_state = "bms_precharged_waiting_for_pcs"
        elif rack_runtime_ready:
            system_state = "rack_precharged"
        else:
            system_state = "transitioning"
        return {
            "system_state": system_state,
            "stopped_safe": stopped_safe,
            "ready_for_power": pcs_ready,
            "pcs_ready_state": self._pcs_ready_state(state),
            "voltage_match": dc_ready,
            "active_direction": "charge" if setpoint < 0 else "discharge" if setpoint > 0 else None,
            "steps": steps,
            "automatic_run": deepcopy(runtime),
            "hard_blocked": bool(
                blockers.get("emergency_stop_fault")
                or blockers.get("documented_critical_fault")
                or summary.get("pcs_fault_shutdown")
            ),
        }

    def status(
        self,
        pair_id: str,
        *,
        fresh: bool = False,
        wait_for_refresh: bool = True,
        return_cached_if_busy: bool = False,
        refresh_wait_timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Return cached runtime state or a bounded engineering live refresh.

        Normal UI polling must use ``fresh=False``. A live refresh performs many
        fieldbus transactions and is therefore protected by per-pair and global
        single-flight gates. Internal control logic may wait for the bounded lane;
        HTTP engineering requests should use ``wait_for_refresh=False``.
        """
        pair = self._pair(pair_id)
        if not fresh:
            return self._runtime_snapshot(pair_id)

        pair_gate = self._status_refresh_locks[pair_id]
        if not self._acquire_refresh_gate(
            pair_gate,
            wait=wait_for_refresh,
            timeout_seconds=refresh_wait_timeout_seconds,
        ):
            return self._busy_live_status(
                pair_id,
                reason="pair_refresh_in_progress",
                return_cached_if_busy=return_cached_if_busy,
            )

        global_acquired = False
        started_monotonic = time.monotonic()
        try:
            global_acquired = self._acquire_refresh_gate(
                self._status_refresh_global,
                wait=wait_for_refresh,
                timeout_seconds=refresh_wait_timeout_seconds,
            )
            if not global_acquired:
                return self._busy_live_status(
                    pair_id,
                    reason="global_refresh_lane_busy",
                    return_cached_if_busy=return_cached_if_busy,
                )

            started_at = now_iso()
            with self._lock:
                stats = self._status_refresh_stats[pair_id]
                stats["active"] = True
                stats["started"] += 1
                stats["last_started_at"] = started_at
                stats["last_error"] = None

            try:
                result = self._read_live_status(pair_id, pair)
            except Exception as error:
                with self._lock:
                    stats = self._status_refresh_stats[pair_id]
                    stats["failed"] += 1
                    stats["last_error"] = str(error)
                raise

            duration_ms = (time.monotonic() - started_monotonic) * 1000.0
            completed_at = now_iso()
            result["refresh"] = {
                "requested_fresh": True,
                "source": "live_hardware",
                "busy": False,
                "stale": False,
                "started_at": started_at,
                "completed_at": completed_at,
                "duration_ms": round(duration_ms, 3),
            }
            with self._lock:
                self._last_live_status[pair_id] = deepcopy(result)
                stats = self._status_refresh_stats[pair_id]
                stats["completed"] += 1
                stats["last_completed_at"] = completed_at
                stats["last_duration_ms"] = round(duration_ms, 3)
            return result
        finally:
            with self._lock:
                self._status_refresh_stats[pair_id]["active"] = False
            if global_acquired:
                self._status_refresh_global.release()
            pair_gate.release()

    def _read_live_status(
        self, pair_id: str, pair: ControlPairConfig
    ) -> dict[str, Any]:
        rack_asset = f"bms_rack_{pair.rack_id}"
        reads: dict[str, dict[str, Any] | None] = {}
        errors: list[dict[str, str]] = []

        requests = [
            ("bank_external_fault", self.bms_driver.read_point, "bms_bank", "external_fault_state"),
            ("bank_level1_alarm_1", self.bms_driver.read_point, "bms_bank", "external_level1_alarm"),
            ("bank_level1_alarm_2", self.bms_driver.read_point, "bms_bank", "bcu_external_lv1_alm_sum_ii"),
            ("bank_rack_fault", self.bms_driver.read_point, "bms_bank", "rack_fault"),
            ("bank_fault_summary_2", self.bms_driver.read_point, "bms_bank", "fault_info_sum2"),
            ("bank_rack_enable_state", self.bms_driver.read_point, "bms_bank", "rack_enable_state_l16"),
            ("rack_external_fault", self.bms_driver.read_point, rack_asset, "bcu_external_fault_alarm"),
            ("rack_critical_1", self.bms_driver.read_point, rack_asset, "external_critical"),
            ("rack_critical_2", self.bms_driver.read_point, rack_asset, "external_stop_alarm2"),
            ("rack_run_state", self.bms_driver.read_point, rack_asset, "bcu_run_state"),
            ("rack_voltage", self.bms_driver.read_point, rack_asset, "vrack"),
            ("rack_charge_limit", self.bms_driver.read_point, rack_asset, "irack_chg_limit"),
            ("rack_discharge_limit", self.bms_driver.read_point, rack_asset, "irack_dsg_limit"),
            ("insulation_command", self.bms_driver.read_point, rack_asset, "start_insulation_sampleing"),
            ("insulation_resistance", self.bms_driver.read_point, rack_asset, "ir"),
            ("insulation_resistance_pos", self.bms_driver.read_point, rack_asset, "ir_pos"),
            ("insulation_resistance_neg", self.bms_driver.read_point, rack_asset, "ir_neg"),
            ("precharge_state", self.bms_driver.read_point, rack_asset, "pre_charge_state"),
            ("precharge_command", self.bms_driver.read_point, rack_asset, "start_pre_chg_operate"),
            ("contactor_state", self.bms_driver.read_point, rack_asset, "contactor_state"),
            ("pcs_dc_bus_voltage", self.pcs_driver.read_point, pair.pcs_asset_id, "dc_bus_voltage"),
            ("pcs_battery_voltage", self.pcs_driver.read_point, pair.pcs_asset_id, "battery_voltage"),
            ("pcs_operating_state", self.pcs_driver.read_point, pair.pcs_asset_id, "operating_state"),
            ("pcs_status_word_1", self.pcs_driver.read_point, pair.pcs_asset_id, "status_word_1"),
            ("pcs_status_word_2", self.pcs_driver.read_point, pair.pcs_asset_id, "status_word_2"),
            ("pcs_input_fault_word", self.pcs_driver.read_point, pair.pcs_asset_id, "reg_1210"),
            ("pcs_system_fault_ext3", self.pcs_driver.read_point, pair.pcs_asset_id, "reg_121a"),
            ("pcs_actual_power", self.pcs_driver.read_point, pair.pcs_asset_id, "grid_active_power"),
            ("pcs_on_off_command", self.pcs_driver.read_point, pair.pcs_asset_id, "remote_on_off_command"),
            ("pcs_remote_local_mode", self.pcs_driver.read_point, pair.pcs_asset_id, "remote_local_mode"),
            ("pcs_product_mode", self.pcs_driver.read_point, pair.pcs_asset_id, "product_run_mode"),
            ("pcs_pq_mode", self.pcs_driver.read_point, pair.pcs_asset_id, "pq_work_mode"),
            ("pcs_power_setpoint", self.pcs_driver.read_point, pair.pcs_asset_id, "active_power_setpoint"),
        ]
        for name, function, *args in requests:
            value, error = self._read_safely(name, function, *args)
            reads[name] = value
            if error:
                errors.append(error)

        return self._build_status_from_reads(
            pair_id,
            pair,
            reads,
            errors,
        )

    def precheck(self, pair_id: str, direction: Direction, requested_power_kw: float) -> dict[str, Any]:
        pair = self._pair(pair_id)
        requested = float(requested_power_kw)
        status = self.status(pair_id, fresh=True)
        summary = status["summary"]
        checks: dict[str, bool] = {
            "all_required_reads_ok": not status["errors"],
            "rack_voltage_valid": bool(summary["rack_voltage_valid"]),
            "precharge_success": bool(summary.get("precharge_success")),
            "contactors_ready": bool(summary.get("contactors_ready")),
            "pcs_remote_feedback": summary.get("pcs_remote_feedback") is True,
            "pcs_ready_state": self._pcs_ready_state(summary.get("pcs_operating_state")),
            "pcs_dc_breaker_feedback_closed": bool(summary.get("pcs_dc_breaker_feedback_closed")),
            "pcs_dc_bus_valid": bool(summary.get("pcs_dc_bus_valid")),
            "pcs_input_and_dc_bus_match": self._voltages_match(
                summary.get("pcs_battery_voltage_v"),
                summary.get("pcs_dc_bus_voltage_v"),
            ),
            "pcs_not_fault_shutdown": not bool(summary["pcs_fault_shutdown"]),
            "no_emergency_stop": not bool(summary["blockers"]["emergency_stop_fault"]),
            "no_system_fault": not bool(summary["blockers"]["system_fault"]),
            "requested_power_non_negative": requested >= 0,
            "requested_power_within_240kw_limit": requested <= self.config.max_abs_power_kw,
        }
        if direction == "charge":
            current_limit = summary["rack_charge_current_limit_a"]
            dynamic_limit = summary["bms_charge_power_limit_kw"]
            checks["bms_direction_not_prohibited"] = not bool(
                summary["blockers"]["system_charge_prohibited"]
            )
        elif direction == "discharge":
            current_limit = summary["rack_discharge_current_limit_a"]
            dynamic_limit = summary["bms_discharge_power_limit_kw"]
            checks["bms_direction_not_prohibited"] = not bool(
                summary["blockers"]["system_discharge_prohibited"]
            )
        else:
            raise ValueError("Direction must be charge or discharge")
        checks["bms_current_limit_available"] = (
            current_limit is not None
            and float(current_limit) >= self.config.minimum_bms_current_limit_a
        )
        if self.config.enforce_dynamic_bms_power_limit:
            checks["requested_power_within_dynamic_bms_limit"] = (
                dynamic_limit is not None
                and requested <= float(dynamic_limit) + 1e-9
            )
        effective_limit = self.config.max_abs_power_kw
        if dynamic_limit is not None:
            effective_limit = min(effective_limit, float(dynamic_limit))
        result = {
            "ok": all(checks.values()),
            "pair": pair.model_dump(),
            "direction": direction,
            "requested_power_kw": requested,
            "effective_power_limit_kw": round(effective_limit, 3),
            "checks": checks,
            "permission_diagnostics": {
                "source": summary["blockers"].get("direction_permission_source"),
                "global_summary_system_full": summary["blockers"].get("global_summary_system_full"),
                "global_summary_system_empty": summary["blockers"].get("global_summary_system_empty"),
                "global_summary_direction_bits_contradictory": summary["blockers"].get(
                    "global_summary_direction_bits_contradictory"
                ),
                "note": (
                    "Global BAU 0x1001 full/empty bits are diagnostic only for individual-pair control; "
                    "the selected rack current limit and documented detailed fault words are enforced."
                ),
            },
            "status": status,
            "timestamp": now_iso(),
        }
        self._update_runtime(
            pair_id,
            stage="precheck_passed" if result["ok"] else "precheck_failed",
            last_action="precheck",
            last_error=None if result["ok"] else [key for key, passed in checks.items() if not passed],
            requested_direction=direction,
            requested_power_kw=requested,
        )
        return result

    def enable_rack(
        self,
        username: str,
        pair_id: str,
        direction: Direction,
        requested_power_kw: float,
        confirmation: str,
    ) -> dict[str, Any]:
        """Compatibility stage; no BAU indexed write is issued.

        Vendor and field validation established that individual Rack 1-4
        runtime operation uses each rack BCU's 0x0402 precharge command. BAU
        0x3005-0x3008 must not be operated by the normal EMS sequence.
        """
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        status = self.status(pair_id, fresh=True)
        response = {
            "ok": True,
            "skipped": True,
            "stage": "individual_rack_enable_not_required",
            "write": None,
            "pair": pair.model_dump(),
            "note": (
                "No BAU 0x3005-0x3008 write was sent. Start the selected rack through "
                f"bms_rack_{pair.rack_id} BCU 0x0402 precharge control."
            ),
            "status": status,
        }
        self._update_runtime(
            pair_id,
            stage=response["stage"],
            last_action="enable_rack_skipped",
            last_error=None,
        )
        self._audit(
            username,
            pair,
            "enable_rack_skipped",
            {"direction": direction, "power_kw": requested_power_kw},
            response,
        )
        return response

    def verify_insulation(self, pair_id: str) -> dict[str, Any]:
        """Read insulation command, resistance measurements and safety flags.

        The vendor sheet exposes IR/IR+/IR- measurements but does not define a
        project-specific pass threshold in the supplied control flow. This
        method therefore reports measurements without claiming that insulation
        is acceptable for precharge.
        """
        pair = self._pair(pair_id)
        status = self.status(pair_id, fresh=True)
        summary = status["summary"]
        result = {
            "ok": not status["errors"],
            "stage": "insulation_observed",
            "pair": pair.model_dump(),
            "insulation_command": summary.get("insulation_command"),
            "insulation_resistance_kohm": summary.get("insulation_resistance_kohm"),
            "insulation_resistance_pos_kohm": summary.get("insulation_resistance_pos_kohm"),
            "insulation_resistance_neg_kohm": summary.get("insulation_resistance_neg_kohm"),
            "documented_critical_fault": bool(summary["blockers"]["documented_critical_fault"]),
            "emergency_stop_fault": bool(summary["blockers"]["emergency_stop_fault"]),
            "rack_enabled": summary.get("rack_enabled"),
            "rack_voltage_v": summary.get("rack_voltage_v"),
            "precharge_command": summary.get("precharge_command"),
            "precharge_state": summary.get("precharge_state"),
            "contactors_ready": summary.get("contactors_ready"),
            "errors": status["errors"],
            "threshold_validated": False,
            "next_action": "Review IR/IR+/IR- with the BMS vendor; do not infer precharge readiness until the vendor confirms the acceptable threshold and feedback semantics.",
            "timestamp": now_iso(),
        }
        self._update_runtime(
            pair_id,
            stage="insulation_observed",
            last_action="verify_insulation",
            last_error=status["errors"] or None,
        )
        return result

    def start_insulation(self, username: str, pair_id: str, confirmation: str) -> dict[str, Any]:
        """Request BCU insulation sampling at absolute register 0x0401.

        This is a manual commissioning stage. It writes only the vendor-defined
        start value 1 and does not write 0 afterward because the supplied sheet
        does not require an explicit clear. It waits at least three seconds
        before collecting follow-up measurements, matching the vendor note that
        the command must not be retriggered within three seconds.
        """
        raise ValueError(
            "Manual BMS insulation command 0x0401 is disabled: the BMS vendor confirmed "
            "that insulation sampling is handled automatically by the BMS."
        )

        # Historical implementation retained below but unreachable.
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        status_before = self.status(pair_id, fresh=True)
        summary = status_before["summary"]
        pcs_state = summary.get("pcs_operating_state")
        pcs_setpoint = summary.get("pcs_power_setpoint_kw")
        pcs_actual = summary.get("pcs_actual_power_kw")
        precharge_command = summary.get("precharge_command")
        precharge_state = summary.get("precharge_state")
        safe_checks = {
            "all_required_reads_ok": not status_before["errors"],
            "rack_voltage_valid": bool(summary.get("rack_voltage_valid")),
            "pcs_stopped": pcs_state is not None and int(pcs_state) == PCS_STOPPED_STATE,
            "pcs_setpoint_zero": pcs_setpoint is not None and abs(float(pcs_setpoint)) <= PCS_ZERO_SETPOINT_TOLERANCE_KW,
            "pcs_actual_power_zero": pcs_actual is not None and abs(float(pcs_actual)) <= PCS_ZERO_ACTUAL_POWER_TOLERANCE_KW,
            "positive_contactor_open": not bool(summary.get("positive_contactor_closed")),
            "negative_contactor_open": not bool(summary.get("negative_contactor_closed")),
            "precharge_command_idle": precharge_command is not None and int(precharge_command) == 0,
            "precharge_state_idle": precharge_state is not None and int(precharge_state) == 0,
            "no_emergency_stop": not bool(summary["blockers"]["emergency_stop_fault"]),
            "no_documented_critical_fault": not bool(summary["blockers"]["documented_critical_fault"]),
        }
        if not all(safe_checks.values()):
            failed = [key for key, passed in safe_checks.items() if not passed]
            raise ValueError(f"Insulation-sampling safety precheck failed: {failed}")

        rack_asset = f"bms_rack_{pair.rack_id}"
        try:
            write = self.bms_driver.write_point(
                rack_asset, "start_insulation_sampleing", BMS_INSULATION_START_VALUE
            )
            time.sleep(BMS_INSULATION_MIN_RETRIGGER_SECONDS)
            samples: list[dict[str, Any]] = []
            critical_fault_detected = False
            for index in range(3):
                observed = self.status(pair_id, fresh=True)
                observed_summary = observed["summary"]
                sample = {
                    "sample": index + 1,
                    "insulation_command": observed_summary.get("insulation_command"),
                    "insulation_resistance_kohm": observed_summary.get("insulation_resistance_kohm"),
                    "insulation_resistance_pos_kohm": observed_summary.get("insulation_resistance_pos_kohm"),
                    "insulation_resistance_neg_kohm": observed_summary.get("insulation_resistance_neg_kohm"),
                    "documented_critical_fault": bool(observed_summary["blockers"]["documented_critical_fault"]),
                    "emergency_stop_fault": bool(observed_summary["blockers"]["emergency_stop_fault"]),
                    "rack_enabled": observed_summary.get("rack_enabled"),
                    "precharge_state": observed_summary.get("precharge_state"),
                    "errors": observed["errors"],
                }
                samples.append(sample)
                critical_fault_detected = critical_fault_detected or sample["documented_critical_fault"]
                if index < 2:
                    time.sleep(self.config.sample_interval_seconds)
            response = {
                "ok": not critical_fault_detected and all(not item["errors"] for item in samples),
                "stage": "insulation_sampling_observed" if not critical_fault_detected else "insulation_sampling_fault_detected",
                "write": write,
                "safe_checks": safe_checks,
                "minimum_retrigger_delay_seconds": BMS_INSULATION_MIN_RETRIGGER_SECONDS,
                "samples": samples,
                "threshold_validated": False,
                "next_action": (
                    "Review IR/IR+/IR- values with the BMS vendor before issuing precharge at 0x0402."
                    if not critical_fault_detected
                    else "Do not issue precharge; inspect the new documented BMS fault and return to safe-stop."
                ),
            }
            self._update_runtime(
                pair_id,
                stage=response["stage"],
                last_action="start_insulation",
                last_error=None if response["ok"] else "Insulation sampling produced a fault or read error",
            )
            self._audit(
                username,
                pair,
                "start_insulation",
                {"register": "0x0401", "value": 1, "explicit_clear": False, "safe_checks": safe_checks},
                response,
                "success" if response["ok"] else "failed",
            )
            return response
        except Exception as error:
            self._update_runtime(pair_id, stage="error", last_action="start_insulation", last_error=str(error))
            self._audit(
                username,
                pair,
                "start_insulation",
                {"register": "0x0401", "value": 1},
                {"ok": False, "error": str(error)},
                "failed",
            )
            raise

    def start_precharge(self, username: str, pair_id: str, confirmation: str) -> dict[str, Any]:
        """Start the selected rack directly through its BCU 0x0402 command.

        No BAU 0x3005-0x3008 indexed rack-enable command is required or sent.
        """
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        status = self.status(pair_id, fresh=True)
        summary = status["summary"]

        if bool(summary.get("precharge_success")) and bool(summary.get("contactors_ready")):
            response = {
                "ok": True,
                "stage": "precharge_already_complete",
                "write": None,
                "status": status,
                "note": "Selected rack BCU already reports precharge state 3 and both contactors closed.",
            }
            self._update_runtime(
                pair_id,
                stage=response["stage"],
                last_action="start_precharge",
                last_error=None,
            )
            return response

        checks = {
            "all_required_reads_ok": not status["errors"],
            "rack_voltage_valid": bool(summary.get("rack_voltage_valid")),
            "pcs_stopped": int(summary.get("pcs_operating_state") or 0) == PCS_STOPPED_STATE,
            "pcs_setpoint_zero": abs(float(summary.get("pcs_power_setpoint_kw") or 0.0))
            <= PCS_ZERO_SETPOINT_TOLERANCE_KW,
            "pcs_actual_power_zero": abs(float(summary.get("pcs_actual_power_kw") or 0.0))
            <= PCS_ZERO_ACTUAL_POWER_TOLERANCE_KW,
            "no_emergency_stop": not bool(summary["blockers"]["emergency_stop_fault"]),
            "no_documented_critical_fault": not bool(
                summary["blockers"]["documented_critical_fault"]
            ),
            "pcs_not_fault_shutdown": not bool(summary.get("pcs_fault_shutdown")),
        }
        if not all(checks.values()):
            raise ValueError(
                f"Individual-rack precharge check failed: {[key for key, ok in checks.items() if not ok]}"
            )

        rack_asset = f"bms_rack_{pair.rack_id}"
        try:
            write = self.bms_driver.write_point(rack_asset, "start_pre_chg_operate", 1)
            response = {
                "ok": True,
                "stage": "precharge_requested",
                "write": write,
                "precheck": checks,
                "control_path": {
                    "asset_id": rack_asset,
                    "register": "0x0402",
                    "value": 1,
                    "bau_indexed_enable_used": False,
                },
            }
            self._update_runtime(
                pair_id,
                stage="precharge_requested",
                last_action="start_precharge",
                last_error=None,
            )
            self._audit(username, pair, "start_precharge", 1, response)
            return response
        except Exception as error:
            self._update_runtime(
                pair_id,
                stage="error",
                last_action="start_precharge",
                last_error=str(error),
            )
            self._audit(
                username,
                pair,
                "start_precharge",
                1,
                {"ok": False, "error": str(error)},
                "failed",
            )
            raise

    def _bms_fault_snapshot(self, pair: ControlPairConfig) -> dict[str, Any]:
        rack_asset = f"bms_rack_{pair.rack_id}"
        requests = [
            ("bank_external_fault", "bms_bank", "external_fault_state"),
            ("bank_level1_alarm_1", "bms_bank", "external_level1_alarm"),
            ("bank_level1_alarm_2", "bms_bank", "bcu_external_lv1_alm_sum_ii"),
            ("bank_rack_fault", "bms_bank", "rack_fault"),
            ("bank_fault_summary_2", "bms_bank", "fault_info_sum2"),
            ("rack_external_fault", rack_asset, "bcu_external_fault_alarm"),
            ("rack_critical_1", rack_asset, "external_critical"),
            ("rack_critical_2", rack_asset, "external_stop_alarm2"),
            ("rack_run_state", rack_asset, "bcu_run_state"),
            ("precharge_state", rack_asset, "pre_charge_state"),
            ("precharge_command", rack_asset, "start_pre_chg_operate"),
            ("contactor_state", rack_asset, "contactor_state"),
        ]
        points: dict[str, Any] = {}
        errors: list[dict[str, str]] = []
        for name, asset_id, point_key in requests:
            point, error = self._read_safely(name, self.bms_driver.read_point, asset_id, point_key)
            points[name] = point
            if error:
                errors.append(error)

        external = points.get("bank_external_fault") or {}
        external_bits = external.get("bitfields", {})
        rack_external = points.get("rack_external_fault") or {}
        rack_external_bits = rack_external.get("bitfields", {})
        return {
            "timestamp": now_iso(),
            "system_fault": external_bits.get("system_fault") == 1,
            "emergency_stop_fault": external_bits.get("emergency_stop_fault") == 1,
            "charge_prohibited": external_bits.get("system_full") == 1,
            "discharge_prohibited": external_bits.get("system_empty") == 1,
            "external_fault_raw": external.get("raw"),
            "external_fault_bits": external_bits,
            "rack_external_fault_raw": rack_external.get("raw"),
            "rack_external_fault_bits": rack_external_bits,
            "points": points,
            "errors": errors,
        }

    def recover_bms(self, username: str, pair_id: str, confirmation: str) -> dict[str, Any]:
        """Trigger BAU one-click recovery only from a verified de-energized state.

        This is a manual commissioning action. It does not bypass an active
        fault, start a rack, close contactors, or start the PCS. The command
        writes the documented trigger value 1 to BAU register 0x3047 and lets
        the BMS manage/reset the command internally, then reports whether the
        BMS summary fault cleared. The protocol defines value 0 as invalid, so
        the gateway must not explicitly write 0 after the trigger.
        """
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        status_before = self.status(pair_id, fresh=True)
        summary = status_before["summary"]

        pcs_state = summary.get("pcs_operating_state")
        pcs_setpoint = summary.get("pcs_power_setpoint_kw")
        pcs_actual = summary.get("pcs_actual_power_kw")
        precharge_command = summary.get("precharge_command")
        safe_checks = {
            "all_required_reads_ok": not status_before["errors"],
            "pcs_stopped": pcs_state is not None and int(pcs_state) == PCS_STOPPED_STATE,
            "pcs_setpoint_zero": pcs_setpoint is not None and abs(float(pcs_setpoint)) <= PCS_ZERO_SETPOINT_TOLERANCE_KW,
            "pcs_actual_power_zero": pcs_actual is not None and abs(float(pcs_actual)) <= PCS_ZERO_ACTUAL_POWER_TOLERANCE_KW,
            "positive_contactor_open": not bool(summary.get("positive_contactor_closed")),
            "negative_contactor_open": not bool(summary.get("negative_contactor_closed")),
            "precharge_command_idle": precharge_command is not None and int(precharge_command) == BMS_RECOVERY_IDLE_VALUE,
            "no_emergency_stop": not bool(summary["blockers"]["emergency_stop_fault"]),
            "system_fault_present": bool(summary["blockers"]["system_fault"]),
        }
        if not all(safe_checks.values()):
            failed = [key for key, passed in safe_checks.items() if not passed]
            raise ValueError(f"BMS recovery safety precheck failed: {failed}")

        before_faults = self._bms_fault_snapshot(pair)
        actions: list[dict[str, Any]] = []
        errors: list[str] = []
        try:
            actions.append(
                self.bms_driver.write_point(
                    "bms_bank", "one_click_revert", BMS_RECOVERY_TRIGGER_VALUE
                )
            )
            time.sleep(self.config.sample_interval_seconds)
        except Exception as error:
            errors.append(f"bms_recovery_trigger: {error}")

        samples: list[dict[str, Any]] = []
        fault_cleared = False
        if not errors:
            for index in range(10):
                current = self.status(pair_id, fresh=True)
                sample = {
                    "sample": index + 1,
                    "system_fault": bool(current["summary"]["blockers"]["system_fault"]),
                    "external_fault_raw": (current["points"].get("bank_external_fault") or {}).get("raw"),
                    "rack_enabled": current["summary"].get("rack_enabled"),
                    "precharge_state": current["summary"].get("precharge_state"),
                    "contactors_ready": current["summary"].get("contactors_ready"),
                }
                samples.append(sample)
                if not sample["system_fault"]:
                    fault_cleared = True
                    break
                time.sleep(self.config.sample_interval_seconds)

        after_faults = self._bms_fault_snapshot(pair)
        stage = "bms_recovered" if fault_cleared else "bms_recovery_requested_fault_still_active"
        response = {
            "ok": not errors,
            "stage": stage,
            "fault_cleared": fault_cleared,
            "safe_checks": safe_checks,
            "actions": actions,
            "errors": errors,
            "before_faults": before_faults,
            "samples": samples,
            "after_faults": after_faults,
            "next_action": (
                "Re-run status and staged rack-enable precheck"
                if fault_cleared
                else "Do not enable rack; identify vendor-specific/latched fault or clear it from BMS HMI"
            ),
        }
        self._update_runtime(
            pair_id,
            stage=stage,
            last_action="recover_bms",
            last_error=errors or (None if fault_cleared else "BMS system fault remains active"),
        )
        self._audit(
            username,
            pair,
            "recover_bms",
            {"register": "0x3047", "trigger_value": 1, "explicit_clear": False, "safe_checks": safe_checks},
            response,
            "success" if not errors else "failed",
        )
        if errors:
            raise RuntimeError("; ".join(errors))
        return response

    def verify_ready(self, pair_id: str) -> dict[str, Any]:
        pair = self._pair(pair_id)
        samples: list[dict[str, Any]] = []
        passed = 0
        for index in range(self.config.valid_samples_required):
            status = self.status(pair_id, fresh=True)
            summary = status["summary"]
            sample_ok = (
                not status["errors"]
                and bool(summary["rack_voltage_valid"])
                and bool(summary["pcs_dc_bus_valid"])
                and bool(summary["contactors_ready"])
                and (bool(summary["precharge_success"]) or not self.config.require_precharge_success)
                and bool(summary["pcs_dc_breaker_feedback_closed"])
                and self._voltages_match(
                    summary.get("pcs_dc_bus_voltage_v"),
                    summary.get("pcs_battery_voltage_v"),
                )
                and self._pcs_ready_state(summary.get("pcs_operating_state"))
                and not bool(summary["pcs_fault_shutdown"])
                and not bool(summary["pcs_dc_soft_start_fault"])
                and not bool(summary["pcs_dc_soft_start_relay_fault"])
                and not bool(summary["blockers"]["emergency_stop_fault"])
                and not bool(summary["blockers"]["system_fault"])
            )
            samples.append({"sample": index + 1, "ok": sample_ok, "summary": summary, "errors": status["errors"]})
            passed += int(sample_ok)
            if index + 1 < self.config.valid_samples_required:
                time.sleep(self.config.sample_interval_seconds)
        result = {
            "ok": passed == self.config.valid_samples_required,
            "pair": pair.model_dump(),
            "passed_samples": passed,
            "required_samples": self.config.valid_samples_required,
            "samples": samples,
            "timestamp": now_iso(),
        }
        self._update_runtime(
            pair_id,
            stage="dc_ready" if result["ok"] else "dc_not_ready",
            last_action="verify_ready",
            last_error=None if result["ok"] else "Readiness conditions not stable",
        )
        return result

    def prepare_pcs_standby(self, username: str, pair_id: str, confirmation: str) -> dict[str, Any]:
        """Deprecated unsafe sequence retained only for API compatibility.

        Hardware validation proved that this PCS must receive BMS DC input
        before the PCS Start command. Starting the PCS while the rack and BMS
        contactors are open caused fault shutdown. Use configure_pcs(), then
        start_precharge() on the selected rack BCU, then start_pcs().
        """
        self._pair(pair_id)
        self._require_write_gates(confirmation)
        raise ValueError(
            "prepare-pcs-standby is disabled: field validation requires BMS precharge/contactors first, then PCS Start at 0 kW"
        )

    def configure_pcs(self, username: str, pair_id: str, confirmation: str) -> dict[str, Any]:
        """Configure PCS Remote/PQ/constant-power at zero while keeping it stopped.

        This matches the field-validated sequence: PCS is configured first,
        the selected rack BCU precharge closes the main contactors, and only
        then is the PCS Start command issued.
        """
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        before = self.status(pair_id, fresh=True)
        summary = before["summary"]
        state = int(summary.get("pcs_operating_state") or 0)
        checks = {
            "all_required_reads_ok": not before["errors"],
            "pcs_stopped": state == PCS_STOPPED_STATE,
            "pcs_not_fault_shutdown": not bool(summary.get("pcs_fault_shutdown")),
            "pcs_actual_power_zero": abs(float(summary.get("pcs_actual_power_kw") or 0.0)) <= PCS_ZERO_ACTUAL_POWER_TOLERANCE_KW,
            "no_emergency_stop": not bool(summary["blockers"]["emergency_stop_fault"]),
            "no_documented_critical_fault": not bool(summary["blockers"]["documented_critical_fault"]),
        }
        if not all(checks.values()):
            raise ValueError(f"PCS configuration precheck failed: {[key for key, ok in checks.items() if not ok]}")

        commands = [
            ("active_power_setpoint", 0.0),
            ("remote_on_off_command", PCS_STOP_VALUE),
            ("remote_local_mode", PCS_REMOTE_VALUE),
            ("product_run_mode", PCS_PQ_PRODUCT_MODE),
            ("pq_work_mode", PCS_CONSTANT_POWER_MODE),
        ]
        writes: list[dict[str, Any]] = []
        try:
            for key, value in commands:
                writes.append(self.pcs_driver.write_point(pair.pcs_asset_id, key, value))
            verified = self.status(pair_id, fresh=True)
            verified_summary = verified["summary"]
            verification = {
                "pcs_stopped": int(verified_summary.get("pcs_operating_state") or 0) == PCS_STOPPED_STATE,
                "remote_feedback": verified_summary.get("pcs_remote_feedback") is True,
                "setpoint_zero": abs(float(verified_summary.get("pcs_power_setpoint_kw") or 0.0)) <= PCS_ZERO_SETPOINT_TOLERANCE_KW,
                "actual_power_zero": abs(float(verified_summary.get("pcs_actual_power_kw") or 0.0)) <= PCS_ZERO_ACTUAL_POWER_TOLERANCE_KW,
            }
            if not all(verification.values()):
                raise RuntimeError(f"PCS configuration readback failed: {[key for key, ok in verification.items() if not ok]}")
            response = {
                "ok": True,
                "stage": "pcs_configured_stopped_zero_power",
                "writes": writes,
                "precheck": checks,
                "verification": verification,
                "status": verified,
            }
            self._update_runtime(pair_id, stage=response["stage"], last_action="configure_pcs", last_error=None)
            self._audit(username, pair, "configure_pcs", dict(commands), response)
            return response
        except Exception as error:
            self._update_runtime(pair_id, stage="error", last_action="configure_pcs", last_error=str(error))
            self._audit(username, pair, "configure_pcs", dict(commands), {"ok": False, "error": str(error), "writes": writes}, "failed")
            raise

    def start_pcs(self, username: str, pair_id: str, confirmation: str) -> dict[str, Any]:
        """Start PCS only after BMS precharge has energized the PCS input.

        Field validation on 2026-07-28 proved the required order:
        BMS precharge/contactors first, then PCS Start at a 0 kW setpoint. The
        PCS progresses through soft-start/self-test and closes its internal DC
        breaker before becoming ready.
        """
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        before = self.status(pair_id, fresh=True)
        summary = before["summary"]
        input_voltage = summary.get("pcs_battery_voltage_v")
        rack_voltage = summary.get("rack_voltage_v")
        checks = {
            "all_required_reads_ok": not before["errors"],
            "rack_enabled": summary.get("rack_enabled") == 1,
            "precharge_success": bool(summary.get("precharge_success")),
            "contactors_ready": bool(summary.get("contactors_ready")),
            "rack_voltage_valid": bool(summary.get("rack_voltage_valid")),
            "pcs_input_energized": self._voltages_match(rack_voltage, input_voltage),
            "pcs_stopped": int(summary.get("pcs_operating_state") or 0) == PCS_STOPPED_STATE,
            "pcs_setpoint_zero": abs(float(summary.get("pcs_power_setpoint_kw") or 0.0)) <= PCS_ZERO_SETPOINT_TOLERANCE_KW,
            "pcs_actual_power_zero": abs(float(summary.get("pcs_actual_power_kw") or 0.0)) <= PCS_ZERO_ACTUAL_POWER_TOLERANCE_KW,
            "no_emergency_stop": not bool(summary["blockers"]["emergency_stop_fault"]),
            "no_documented_critical_fault": not bool(summary["blockers"]["documented_critical_fault"]),
            "pcs_not_fault_shutdown": not bool(summary.get("pcs_fault_shutdown")),
        }
        if not all(checks.values()):
            raise ValueError(f"PCS start-after-precharge check failed: {[key for key, ok in checks.items() if not ok]}")

        samples: list[dict[str, Any]] = []
        try:
            write = self.pcs_driver.write_point(pair.pcs_asset_id, "remote_on_off_command", PCS_START_VALUE)
            deadline = time.monotonic() + max(
                self.config.pcs_start_timeout_seconds,
                self.config.automatic_stage_timeout_seconds,
            )
            while time.monotonic() < deadline:
                current = self.status(pair_id, fresh=True)
                current_summary = current["summary"]
                state = int(current_summary.get("pcs_operating_state") or 0)
                sample = {
                    "timestamp": current["timestamp"],
                    "pcs_operating_state": state,
                    "pcs_input_voltage_v": current_summary.get("pcs_battery_voltage_v"),
                    "pcs_dc_bus_voltage_v": current_summary.get("pcs_dc_bus_voltage_v"),
                    "pcs_dc_breaker_feedback_closed": current_summary.get("pcs_dc_breaker_feedback_closed"),
                    "pcs_dc_soft_start_fault": current_summary.get("pcs_dc_soft_start_fault"),
                    "pcs_dc_soft_start_relay_fault": current_summary.get("pcs_dc_soft_start_relay_fault"),
                    "pcs_actual_power_kw": current_summary.get("pcs_actual_power_kw"),
                    "errors": current.get("errors", []),
                }
                samples.append(sample)
                if state & PCS_FAULT_SHUTDOWN_BIT:
                    raise RuntimeError(f"PCS entered fault shutdown during startup: {state}")
                if bool(current_summary.get("pcs_dc_soft_start_fault")) or bool(current_summary.get("pcs_dc_soft_start_relay_fault")):
                    raise RuntimeError("PCS reported a DC soft-start/relay fault")
                if not bool(current_summary.get("contactors_ready")):
                    raise RuntimeError("BMS main contactor feedback opened during PCS startup")
                if self._pcs_ready_state(state) and current["workflow"]["ready_for_power"]:
                    response = {
                        "ok": True,
                        "stage": "pcs_ready_zero_power",
                        "write": write,
                        "precheck": checks,
                        "samples": samples,
                        "status": current,
                    }
                    self._update_runtime(pair_id, stage=response["stage"], last_action="start_pcs", last_error=None)
                    self._audit(username, pair, "start_pcs", PCS_START_VALUE, response)
                    return response
                time.sleep(self.config.sample_interval_seconds)
            raise TimeoutError("PCS did not complete soft-start/DC-breaker readiness before timeout")
        except Exception as error:
            safety_actions: list[dict[str, Any]] = []
            for key, value in (("active_power_setpoint", 0.0), ("remote_on_off_command", PCS_STOP_VALUE)):
                try:
                    safety_actions.append(self.pcs_driver.write_point(pair.pcs_asset_id, key, value))
                except Exception as stop_error:
                    safety_actions.append({"ok": False, "point_key": key, "error": str(stop_error)})
            failure = {"ok": False, "error": str(error), "precheck": checks, "samples": samples, "automatic_pcs_safe_stop": safety_actions}
            self._update_runtime(pair_id, stage="error", last_action="start_pcs", last_error=str(error), commanded_power_kw=0.0)
            self._audit(username, pair, "start_pcs", PCS_START_VALUE, failure, "failed")
            raise RuntimeError(f"{error}; PCS zero-setpoint/stop was requested automatically") from error

    def set_power(
        self,
        username: str,
        pair_id: str,
        direction: Direction,
        requested_power_kw: float,
        confirmation: str,
    ) -> dict[str, Any]:
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        requested = float(requested_power_kw)
        try:
            response = self._command_power_internal(
                username,
                pair,
                direction,
                requested,
            )
            if self.config.runtime_monitor_enabled and requested > 0:
                self._ensure_runtime_monitor(username, pair)
            return response
        except Exception as error:
            self._update_runtime(pair_id, stage="error", last_action="set_power", last_error=str(error))
            self._audit(
                username,
                pair,
                "set_power",
                {"direction": direction, "power_kw": requested},
                {"ok": False, "error": str(error)},
                "failed",
            )
            raise

    def verify_power(self, pair_id: str) -> dict[str, Any]:
        pair = self._pair(pair_id)
        setpoint = self.pcs_driver.read_point(pair.pcs_asset_id, "active_power_setpoint")
        actual = self.pcs_driver.read_point(pair.pcs_asset_id, "grid_active_power")
        state = self.pcs_driver.read_point(pair.pcs_asset_id, "operating_state")
        return {
            "ok": True,
            "pair": pair.model_dump(),
            "setpoint": setpoint,
            "actual_power": actual,
            "operating_state": state,
            "timestamp": now_iso(),
        }

    def _wait_for_status(
        self,
        pair_id: str,
        predicate: Any,
        *,
        timeout_seconds: float,
        description: str,
        abort_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last_status: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            if abort_event is not None and abort_event.is_set():
                raise RuntimeError("Sequence aborted by operator")
            last_status = self.status(pair_id, fresh=True)
            if predicate(last_status):
                return last_status
            time.sleep(self.config.sample_interval_seconds)
        raise TimeoutError(
            f"Timed out waiting for {description}; last_status={last_status and last_status.get('summary')}"
        )

    def _set_run_step(
        self,
        pair_id: str,
        key: str,
        status: str,
        *,
        message: str | None = None,
        result: Any = None,
    ) -> None:
        with self._lock:
            runtime = self._runtime[pair_id]
            steps = runtime.setdefault("steps", [])
            step = next((item for item in steps if item.get("key") == key), None)
            if step is None:
                step = {"key": key, "label": key.replace("_", " ").title()}
                steps.append(step)
            step["status"] = status
            if status == "running":
                step["started_at"] = now_iso()
            if status in {"success", "failed", "skipped"}:
                step["completed_at"] = now_iso()
            if message is not None:
                step["message"] = message
            if result is not None:
                step["result"] = result
            runtime["last_updated_at"] = now_iso()

    @staticmethod
    def _automatic_step_template() -> list[dict[str, Any]]:
        return [
            {"key": "pcs_configuration", "label": "Configure PCS Remote/PQ/0 kW", "status": "pending"},
            {
                "key": "rack_enable",
                "label": "BAU rack-enable not required; use selected BCU precharge",
                "status": "pending",
            },
            {"key": "bms_precharge", "label": "BMS precharge and close contactors", "status": "pending"},
            {"key": "pcs_start", "label": "Start PCS and complete DC soft-start", "status": "pending"},
            {"key": "power_precheck", "label": "Verify BMS limits and direction permission", "status": "pending"},
            {"key": "power_ramp", "label": "Ramp to requested power", "status": "pending"},
            {"key": "power_tracking", "label": "Verify actual power tracking", "status": "pending"},
        ]

    def _safe_stop_internal(
        self,
        username: str,
        pair: ControlPairConfig,
        *,
        open_bms: bool,
        reason: str,
    ) -> dict[str, Any]:
        # Runtime protection and operator stop paths may converge at the same
        # moment. Serialize the physical stop sequence per pair so zero-power,
        # PCS Stop and BMS-open writes cannot interleave.
        with self._safe_stop_locks[pair.pair_id]:
            return self._safe_stop_internal_locked(
                username,
                pair,
                open_bms=open_bms,
                reason=reason,
            )

    def _safe_stop_internal_locked(
        self,
        username: str,
        pair: ControlPairConfig,
        *,
        open_bms: bool,
        reason: str,
    ) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        errors: list[str] = []
        pair_id = pair.pair_id

        try:
            actions.append(self.pcs_driver.write_point(pair.pcs_asset_id, "active_power_setpoint", 0.0))
        except Exception as error:
            errors.append(f"active_power_setpoint: {error}")

        try:
            self._wait_for_status(
                pair_id,
                lambda item: abs(float(item["summary"].get("pcs_actual_power_kw") or 0.0))
                <= PCS_ZERO_ACTUAL_POWER_TOLERANCE_KW,
                timeout_seconds=min(5.0, self.config.safe_stop_timeout_seconds),
                description="PCS actual power to return to zero",
            )
        except Exception as error:
            errors.append(f"power_zero_verification: {error}")

        try:
            actions.append(self.pcs_driver.write_point(pair.pcs_asset_id, "remote_on_off_command", PCS_STOP_VALUE))
        except Exception as error:
            errors.append(f"remote_on_off_command: {error}")

        if open_bms:
            rack_asset = f"bms_rack_{pair.rack_id}"
            try:
                actions.append(self.bms_driver.write_point(rack_asset, "start_pre_chg_operate", 0))
            except Exception as error:
                errors.append(f"bms_precharge_stop: {error}")

        final_status: dict[str, Any] | None = None
        try:
            def stopped(item: dict[str, Any]) -> bool:
                summary = item["summary"]
                base = (
                    int(summary.get("pcs_operating_state") or 0) == PCS_STOPPED_STATE
                    and abs(float(summary.get("pcs_power_setpoint_kw") or 0.0)) <= PCS_ZERO_SETPOINT_TOLERANCE_KW
                    and abs(float(summary.get("pcs_actual_power_kw") or 0.0)) <= PCS_ZERO_ACTUAL_POWER_TOLERANCE_KW
                )
                if not open_bms:
                    return base
                return (
                    base
                    and int(summary.get("precharge_state") or 0) == 0
                    and not bool(summary.get("positive_contactor_closed"))
                    and not bool(summary.get("negative_contactor_closed"))
                )

            final_status = self._wait_for_status(
                pair_id,
                stopped,
                timeout_seconds=self.config.safe_stop_timeout_seconds,
                description="verified safe-stop feedback",
            )
        except Exception as error:
            errors.append(f"safe_stop_verification: {error}")
            try:
                final_status = self.status(pair_id, fresh=True)
            except Exception:
                final_status = None

        response = {
            "ok": not errors,
            "stage": "stopped" if not open_bms else "stopped_and_bms_open_verified",
            "reason": reason,
            "actions": actions,
            "errors": errors,
            "final_status": final_status,
            "residual_voltage_note": (
                "PCS input/DC-link voltage may decay after contactors open; shutdown success is based on "
                "zero power, PCS stopped, selected rack precharge idle and contactors open."
            ),
        }
        self._update_runtime(
            pair_id,
            stage=response["stage"] if not errors else "safe_stop_incomplete",
            last_action="safe_stop",
            last_error=errors or None,
            commanded_power_kw=0.0,
            requested_power_kw=0.0,
            monitor_active=False,
        )
        self._audit(
            username,
            pair,
            "safe_stop",
            {"open_bms": open_bms, "reason": reason},
            response,
            "success" if not errors else "failed",
        )
        return response

    def safe_stop(
        self,
        username: str,
        pair_id: str,
        confirmation: str,
        *,
        open_bms: bool = False,
    ) -> dict[str, Any]:
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        self._abort_events[pair_id].set()
        monitor_quiesce = self._quiesce_runtime_monitor(
            pair_id,
            reason="operator_safe_stop",
        )
        response = self._safe_stop_internal(
            username,
            pair,
            open_bms=open_bms,
            reason="operator_safe_stop",
        )
        response["runtime_monitor_quiesce"] = monitor_quiesce
        if response["errors"]:
            raise RuntimeError("; ".join(response["errors"]))
        return response

    def zero_power(self, username: str, pair_id: str, confirmation: str) -> dict[str, Any]:
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        write = self.pcs_driver.write_point(pair.pcs_asset_id, "active_power_setpoint", 0.0)
        status = self._wait_for_status(
            pair_id,
            lambda item: abs(float(item["summary"].get("pcs_actual_power_kw") or 0.0))
            <= PCS_ZERO_ACTUAL_POWER_TOLERANCE_KW,
            timeout_seconds=self.config.power_tracking_timeout_seconds,
            description="actual power to return to zero",
        )
        response = {"ok": True, "stage": "zero_power", "write": write, "status": status}
        self._update_runtime(
            pair_id,
            stage="zero_power",
            last_action="zero_power",
            last_error=None,
            requested_power_kw=0.0,
            commanded_power_kw=0.0,
        )
        self._audit(username, pair, "zero_power", 0.0, response)
        return response

    def _command_power_internal(
        self,
        username: str,
        pair: ControlPairConfig,
        direction: Direction,
        power_kw: float,
    ) -> dict[str, Any]:
        precheck = self.precheck(pair.pair_id, direction, power_kw)
        if not precheck["ok"]:
            failed = [key for key, value in precheck["checks"].items() if not value]
            raise ValueError(f"Power precheck failed: {failed}")
        ready = self.verify_ready(pair.pair_id)
        if not ready["ok"]:
            raise ValueError("BMS contactor/PCS DC readiness verification failed")
        signed = -float(power_kw) if direction == "charge" else float(power_kw)
        write = self.pcs_driver.write_point(pair.pcs_asset_id, "active_power_setpoint", signed)
        response = {
            "ok": True,
            "stage": "power_commanded",
            "direction": direction,
            "requested_power_kw": float(power_kw),
            "commanded_signed_power_kw": signed,
            "effective_power_limit_kw": precheck["effective_power_limit_kw"],
            "write": write,
        }
        self._update_runtime(
            pair.pair_id,
            stage="power_commanded",
            last_action="set_power",
            last_error=None,
            requested_direction=direction,
            requested_power_kw=float(power_kw),
            commanded_power_kw=signed,
        )
        self._audit(username, pair, "set_power", {"direction": direction, "power_kw": power_kw}, response)
        return response

    def _ramp_power(
        self,
        username: str,
        pair: ControlPairConfig,
        direction: Direction,
        target_power_kw: float,
        *,
        step_kw: float,
        interval_seconds: float,
        abort_event: threading.Event | None = None,
    ) -> list[dict[str, Any]]:
        target = float(target_power_kw)
        if target <= 0:
            self.pcs_driver.write_point(pair.pcs_asset_id, "active_power_setpoint", 0.0)
            return []
        current_point = self.pcs_driver.read_point(pair.pcs_asset_id, "active_power_setpoint")
        current_signed = float(current_point.get("value") or 0.0)
        expected_sign = -1.0 if direction == "charge" else 1.0
        if current_signed * expected_sign < -PCS_ZERO_SETPOINT_TOLERANCE_KW:
            self.pcs_driver.write_point(pair.pcs_asset_id, "active_power_setpoint", 0.0)
            current_magnitude = 0.0
        else:
            current_magnitude = abs(current_signed)
        writes: list[dict[str, Any]] = []
        next_power = min(target, max(0.0, current_magnitude) + step_kw)
        while current_magnitude + 1e-9 < target:
            if abort_event is not None and abort_event.is_set():
                raise RuntimeError("Sequence aborted by operator")
            command = self._command_power_internal(username, pair, direction, next_power)
            writes.append(command)
            current_magnitude = next_power
            if current_magnitude >= target:
                break
            time.sleep(interval_seconds)
            next_power = min(target, current_magnitude + step_kw)
        return writes

    def _power_tracks_target(
        self,
        pair_id: str,
        direction: Direction,
        target_power_kw: float,
        *,
        abort_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        signed_target = -float(target_power_kw) if direction == "charge" else float(target_power_kw)
        tolerance = max(self.config.power_tracking_tolerance_kw, abs(signed_target) * 0.1)
        return self._wait_for_status(
            pair_id,
            lambda item: (
                abs(float(item["summary"].get("pcs_power_setpoint_kw") or 0.0) - signed_target) <= 0.2
                and abs(float(item["summary"].get("pcs_actual_power_kw") or 0.0) - signed_target) <= tolerance
                and not bool(item["workflow"].get("hard_blocked"))
            ),
            timeout_seconds=self.config.power_tracking_timeout_seconds,
            description=f"actual power to track {signed_target} kW",
            abort_event=abort_event,
        )

    def _require_automatic_gates(self, confirmation: str) -> None:
        if confirmation != self.config.automatic_confirmation_phrase:
            raise PermissionError(
                f"Automatic sequence confirmation must equal {self.config.automatic_confirmation_phrase!r}"
            )
        if not self.config.allow_full_automatic_sequence:
            raise PermissionError("Full automatic sequence is disabled in configuration")
        if not self.config.enabled:
            raise PermissionError("BMS/PCS control sequence is disabled")
        if self.gateway_config.mode != "control_enabled":
            raise PermissionError("Gateway mode must be control_enabled")
        if not self.gateway_config.bms.write_enabled or not self.gateway_config.pcs.write_enabled:
            raise PermissionError("BMS and PCS writes must both be enabled")

    def automatic_start(
        self,
        username: str,
        pair_id: str,
        direction: Direction,
        target_power_kw: float,
        confirmation: str,
        *,
        ramp_step_kw: float | None = None,
        ramp_interval_seconds: float | None = None,
    ) -> dict[str, Any]:
        pair = self._pair(pair_id)
        self._require_automatic_gates(confirmation)
        target = float(target_power_kw)
        if target < 0:
            raise ValueError("Target power must be non-negative; direction carries the sign")
        with self._lock:
            existing = self._sequence_threads.get(pair_id)
            if existing is not None and existing.is_alive():
                raise RuntimeError(f"Automatic sequence already running for {pair_id}")
            run_id = f"seq-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
            abort_event = self._abort_events[pair_id]
            abort_event.clear()
            self._runtime[pair_id].update(
                {
                    "run_id": run_id,
                    "run_mode": "automatic",
                    "run_status": "running",
                    "stage": "automatic_sequence_started",
                    "last_action": "automatic_start",
                    "last_error": None,
                    "started_at": now_iso(),
                    "completed_at": None,
                    "requested_direction": direction,
                    "requested_power_kw": target,
                    "commanded_power_kw": 0.0,
                    "steps": self._automatic_step_template(),
                }
            )
            thread = threading.Thread(
                target=self._automatic_worker,
                name=f"control-sequence-{pair_id}",
                daemon=True,
                args=(
                    username,
                    pair,
                    direction,
                    target,
                    ramp_step_kw or self.config.automatic_power_ramp_step_kw,
                    ramp_interval_seconds or self.config.automatic_power_ramp_interval_seconds,
                    abort_event,
                ),
            )
            self._sequence_threads[pair_id] = thread
            thread.start()
        response = {
            "ok": True,
            "accepted": True,
            "run_status": "accepted",
            "stage": "automatic_sequence_started",
            "message": (
                "Automatic request accepted. Startup, precharge, ramp and power "
                "tracking continue asynchronously; accepted does not mean the "
                "target power has been reached yet."
            ),
            "run_id": run_id,
            "pair_id": pair_id,
            "direction": direction,
            "target_power_kw": target,
            "status_endpoint": f"/api/control-sequence/{pair_id}/status?fresh=false",
            "all_pair_status_endpoint": "/api/control-sequence/status/all",
        }
        self._audit(username, pair, "automatic_start", response, response)
        return response

    def _automatic_worker(
        self,
        username: str,
        pair: ControlPairConfig,
        direction: Direction,
        target_power_kw: float,
        ramp_step_kw: float,
        ramp_interval_seconds: float,
        abort_event: threading.Event,
    ) -> None:
        pair_id = pair.pair_id
        try:
            self._set_run_step(pair_id, "pcs_configuration", "running")
            result = self.configure_pcs(username, pair_id, self.config.confirmation_phrase)
            self._set_run_step(pair_id, "pcs_configuration", "success", result=result)

            self._set_run_step(
                pair_id,
                "rack_enable",
                "skipped",
                message=(
                    "No BAU 0x3005-0x3008 write: individual rack operation uses the selected "
                    "BCU 0x0402 precharge command."
                ),
            )

            self._set_run_step(pair_id, "bms_precharge", "running")
            result = self.start_precharge(username, pair_id, self.config.confirmation_phrase)
            status = self._wait_for_status(
                pair_id,
                lambda item: (
                    bool(item["summary"].get("precharge_success"))
                    and bool(item["summary"].get("contactors_ready"))
                    and self._voltages_match(
                        item["summary"].get("rack_voltage_v"),
                        item["summary"].get("pcs_battery_voltage_v"),
                    )
                ),
                timeout_seconds=self.config.automatic_stage_timeout_seconds,
                description="BMS precharge/contactors and PCS input voltage",
                abort_event=abort_event,
            )
            self._set_run_step(pair_id, "bms_precharge", "success", result={"write": result, "status": status})

            self._set_run_step(pair_id, "pcs_start", "running")
            result = self.start_pcs(username, pair_id, self.config.confirmation_phrase)
            self._set_run_step(pair_id, "pcs_start", "success", result=result)

            self._set_run_step(pair_id, "power_precheck", "running")
            precheck = self.precheck(pair_id, direction, target_power_kw)
            if not precheck["ok"]:
                raise ValueError(
                    f"Power precheck failed: {[key for key, value in precheck['checks'].items() if not value]}"
                )
            self._set_run_step(pair_id, "power_precheck", "success", result=precheck)

            self._set_run_step(pair_id, "power_ramp", "running")
            writes = self._ramp_power(
                username,
                pair,
                direction,
                target_power_kw,
                step_kw=ramp_step_kw,
                interval_seconds=ramp_interval_seconds,
                abort_event=abort_event,
            )
            self._set_run_step(pair_id, "power_ramp", "success", result=writes)

            self._set_run_step(pair_id, "power_tracking", "running")
            tracked = self._power_tracks_target(
                pair_id,
                direction,
                target_power_kw,
                abort_event=abort_event,
            )
            self._set_run_step(pair_id, "power_tracking", "success", result=tracked)
            self._update_runtime(
                pair_id,
                stage="automatic_sequence_complete",
                last_action="automatic_start",
                last_error=None,
                run_status="success",
                completed_at=now_iso(),
            )
            if self.config.runtime_monitor_enabled and target_power_kw > 0:
                self._ensure_runtime_monitor(username, pair)
        except Exception as error:
            for step in self._runtime[pair_id].get("steps", []):
                if step.get("status") == "running":
                    self._set_run_step(pair_id, str(step.get("key")), "failed", message=str(error))
                    break
            stop_result = self._safe_stop_internal(
                username,
                pair,
                open_bms=True,
                reason=f"automatic_sequence_failure: {error}",
            )
            self._update_runtime(
                pair_id,
                stage="automatic_sequence_failed",
                last_action="automatic_start",
                last_error=str(error),
                run_status="failed",
                completed_at=now_iso(),
                commanded_power_kw=0.0,
                failure_safe_stop=stop_result,
            )
            LOGGER.exception("Automatic control sequence failed pair=%s", pair_id)

    def next_step(
        self,
        username: str,
        pair_id: str,
        direction: Direction,
        target_power_kw: float,
        confirmation: str,
    ) -> dict[str, Any]:
        self._require_write_gates(confirmation)
        status = self.status(pair_id, fresh=True)
        summary = status["summary"]
        workflow = status["workflow"]
        state = int(summary.get("pcs_operating_state") or 0)
        pcs_configured_stopped = (
            summary.get("pcs_remote_feedback") is True
            and state == PCS_STOPPED_STATE
            and abs(float(summary.get("pcs_power_setpoint_kw") or 0.0))
            <= PCS_ZERO_SETPOINT_TOLERANCE_KW
        )
        precharge_ready = bool(summary.get("precharge_success")) and bool(
            summary.get("contactors_ready")
        )

        if bool(workflow.get("ready_for_power")):
            target_signed = -float(target_power_kw) if direction == "charge" else float(target_power_kw)
            current_signed = float(summary.get("pcs_power_setpoint_kw") or 0.0)
            if abs(current_signed - target_signed) > 0.2:
                action = "set_power"
                result = self.set_power(
                    username,
                    pair_id,
                    direction,
                    float(target_power_kw),
                    confirmation,
                )
            else:
                action = "complete"
                result = {
                    "ok": True,
                    "stage": "requested_state_already_reached",
                    "status": status,
                }
        elif precharge_ready:
            if state == PCS_STOPPED_STATE:
                action = "start_pcs"
                result = self.start_pcs(username, pair_id, confirmation)
            elif state & PCS_FAULT_SHUTDOWN_BIT:
                raise ValueError(f"PCS is in fault shutdown state {state}")
            else:
                action = "wait_for_pcs_ready"
                result = {
                    "ok": True,
                    "stage": "pcs_startup_in_progress",
                    "status": status,
                }
        elif not pcs_configured_stopped:
            action = "configure_pcs"
            result = self.configure_pcs(username, pair_id, confirmation)
        else:
            action = "start_precharge"
            write = self.start_precharge(username, pair_id, confirmation)
            verified = self._wait_for_status(
                pair_id,
                lambda item: bool(item["summary"].get("precharge_success"))
                and bool(item["summary"].get("contactors_ready")),
                timeout_seconds=self.config.automatic_stage_timeout_seconds,
                description="selected-rack BCU precharge success",
            )
            result = {"write": write, "verified": verified}
        return {
            "ok": True,
            "action": action,
            "result": result,
            "status": self.status(pair_id, fresh=True),
        }

    def abort(
        self,
        username: str,
        pair_id: str,
        confirmation: str,
        *,
        open_bms: bool = True,
    ) -> dict[str, Any]:
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        self._abort_events[pair_id].set()
        monitor_quiesce = self._quiesce_runtime_monitor(
            pair_id,
            reason="operator_abort",
        )
        response = self._safe_stop_internal(
            username,
            pair,
            open_bms=open_bms,
            reason="operator_abort",
        )
        response["runtime_monitor_quiesce"] = monitor_quiesce
        self._update_runtime(
            pair_id,
            run_status="aborted",
            completed_at=now_iso(),
            last_action="abort",
            last_error="Aborted by operator",
        )
        return response

    def _quiesce_runtime_monitor(
        self,
        pair_id: str,
        *,
        reason: str,
        timeout_seconds: float = 5.0,
    ) -> dict[str, Any]:
        """Stop the active runtime monitor before opening the BMS contactors.

        The stop event is checked again after any cache/live read returns. This
        closes the operator-safe-stop race where a monitor could evaluate the
        intentionally opened contactors against the previous non-zero command.
        """
        stop_event = self._monitor_stop_events[pair_id]
        stop_event.set()
        self._update_runtime(
            pair_id,
            commanded_power_kw=0.0,
            requested_power_kw=0.0,
            monitor_stop_requested=True,
            monitor_stop_reason=reason,
        )
        with self._lock:
            thread = self._monitor_threads.get(pair_id)
        was_alive = bool(thread is not None and thread.is_alive())
        if was_alive and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, timeout_seconds))
        still_alive = bool(thread is not None and thread.is_alive())
        return {
            "requested": True,
            "reason": reason,
            "was_alive": was_alive,
            "stopped": not still_alive,
            "timeout_seconds": timeout_seconds,
        }

    def _ensure_runtime_monitor(self, username: str, pair: ControlPairConfig) -> None:
        with self._lock:
            current = self._monitor_threads.get(pair.pair_id)
            if current is not None and current.is_alive():
                return
            self._monitor_stop_events[pair.pair_id].clear()
            thread = threading.Thread(
                target=self._runtime_monitor_worker,
                name=f"control-monitor-{pair.pair_id}",
                daemon=True,
                args=(username, pair),
            )
            self._monitor_threads[pair.pair_id] = thread
            self._runtime[pair.pair_id]["monitor_active"] = True
            thread.start()

    def _runtime_monitor_worker(self, username: str, pair: ControlPairConfig) -> None:
        pair_id = pair.pair_id
        stop_event = self._monitor_stop_events[pair_id]
        unverified_since_monotonic: float | None = None
        unverified_since_iso: str | None = None

        try:
            while True:
                if stop_event.is_set():
                    break
                runtime = self._runtime_snapshot(pair_id)
                expected_commanded = float(runtime.get("commanded_power_kw") or 0.0)
                if abs(expected_commanded) <= PCS_ZERO_SETPOINT_TOLERANCE_KW:
                    break

                status = self._runtime_monitor_status(pair_id, pair)
                # An operator safe-stop may have been requested while the cache
                # or bounded live confirmation was in progress. Exit before
                # interpreting the intentionally changing contactor/limit state.
                if stop_event.is_set():
                    break

                source = status.get("refresh", {}).get("source", "unknown")
                freshness = status.get("refresh", {}).get("freshness", {})
                ages = {
                    key: value.get("age_seconds")
                    for key, value in freshness.items()
                    if isinstance(value, dict)
                }
                verification = status.get("runtime_verification", {})
                verification_deferred = bool(verification.get("deferred"))

                if verification_deferred:
                    now_monotonic = time.monotonic()
                    if unverified_since_monotonic is None:
                        unverified_since_monotonic = now_monotonic
                        unverified_since_iso = now_iso()
                        self.store.event(
                            "runtime_monitor",
                            f"{pair_id} runtime verification deferred",
                            asset_id=pair.pcs_asset_id,
                            payload={
                                "pair_id": pair_id,
                                "reason": verification.get("reason"),
                                "source": source,
                                "policy": "retry_with_grace_window",
                            },
                        )
                    unverified_seconds = max(
                        0.0, now_monotonic - unverified_since_monotonic
                    )
                    reason = str(
                        verification.get("reason")
                        or status.get("refresh", {}).get("busy_reason")
                        or "runtime_verification_deferred"
                    )
                    with self._lock:
                        stats = self._runtime_monitor_stats[pair_id]
                        stats["samples"] += 1
                        stats["deferred_verifications"] += 1
                        stats["consecutive_unverified_samples"] += 1
                        stats["unverified_since"] = unverified_since_iso
                        stats["last_sample_at"] = now_iso()
                        stats["last_source"] = source
                        stats["last_cache_ages_seconds"] = ages
                        stats["last_errors"] = deepcopy(status.get("errors", []))
                        stats["last_violations"] = []
                        stats["last_deferred_reason"] = reason

                    self._update_runtime(
                        pair_id,
                        monitor_state="verification_deferred",
                        monitor_verification_deferred=True,
                        monitor_unverified_since=unverified_since_iso,
                        monitor_unverified_seconds=round(unverified_seconds, 3),
                        monitor_last_warning=reason,
                        monitor_last_sample_at=now_iso(),
                    )

                    if (
                        unverified_seconds
                        < self.config.runtime_monitor_max_unverified_seconds
                    ):
                        if stop_event.wait(
                            self.config.runtime_monitor_interval_seconds
                        ):
                            break
                        continue

                    violations = [
                        "runtime_status_unverified_timeout",
                        f"unverified_seconds={round(unverified_seconds, 3)}",
                        f"reason={reason}",
                    ]
                    self.store.event(
                        "runtime_monitor",
                        f"{pair_id} safe-stop after unverified timeout",
                        asset_id=pair.pcs_asset_id,
                        payload={
                            "pair_id": pair_id,
                            "violations": violations,
                            "max_unverified_seconds": (
                                self.config.runtime_monitor_max_unverified_seconds
                            ),
                        },
                    )
                    stop = self._safe_stop_internal(
                        username,
                        pair,
                        open_bms=True,
                        reason=f"runtime_monitor_violation: {violations}",
                    )
                    with self._lock:
                        stats = self._runtime_monitor_stats[pair_id]
                        stats["last_violations"] = deepcopy(violations)
                        stats["safety_stops"] += 1
                    self._update_runtime(
                        pair_id,
                        stage="runtime_safety_stop",
                        last_action="runtime_monitor",
                        last_error=violations,
                        run_status="failed",
                        completed_at=now_iso(),
                        runtime_safety_stop=stop,
                        monitor_state="failed_unverified_timeout",
                    )
                    return

                recovered_from_deferred = unverified_since_monotonic is not None
                if recovered_from_deferred:
                    self.store.event(
                        "runtime_monitor",
                        f"{pair_id} runtime verification recovered",
                        asset_id=pair.pcs_asset_id,
                        payload={
                            "pair_id": pair_id,
                            "source": source,
                            "verified_at": now_iso(),
                        },
                    )
                unverified_since_monotonic = None
                unverified_since_iso = None
                summary = status["summary"]
                direction_value = runtime.get("requested_direction")
                direction: Direction = (
                    direction_value
                    if direction_value in {"charge", "discharge"}
                    else "charge" if expected_commanded < 0 else "discharge"
                )
                dynamic_limit = (
                    summary.get("bms_charge_power_limit_kw")
                    if direction == "charge"
                    else summary.get("bms_discharge_power_limit_kw")
                )
                prohibited = (
                    summary["blockers"].get("system_charge_prohibited")
                    if direction == "charge"
                    else summary["blockers"].get("system_discharge_prohibited")
                )
                current_limit = (
                    summary.get("rack_charge_current_limit_a")
                    if direction == "charge"
                    else summary.get("rack_discharge_current_limit_a")
                )
                violations: list[str] = []
                if status.get("errors"):
                    violations.append("required_read_error")
                if status["workflow"].get("hard_blocked"):
                    violations.append("hard_fault_or_estop")
                if not bool(summary.get("contactors_ready")):
                    violations.append("bms_contactor_open")
                if not bool(summary.get("pcs_dc_breaker_feedback_closed")):
                    violations.append("pcs_dc_breaker_open")
                if prohibited:
                    violations.append(
                        f"{direction}_prohibited_by_selected_rack_limit_or_detailed_fault"
                    )
                if (
                    current_limit is None
                    or float(current_limit)
                    < self.config.minimum_bms_current_limit_a
                ):
                    violations.append("selected_rack_current_limit_unavailable")
                if (
                    dynamic_limit is None
                    or abs(expected_commanded) > float(dynamic_limit) + 1e-9
                ):
                    violations.append("bms_dynamic_power_limit_below_command")

                verified_at = now_iso()
                with self._lock:
                    stats = self._runtime_monitor_stats[pair_id]
                    stats["samples"] += 1
                    if source == "background_poll_cache":
                        stats["cache_samples"] += 1
                    if recovered_from_deferred:
                        stats["verification_recoveries"] += 1
                    stats["consecutive_unverified_samples"] = 0
                    stats["unverified_since"] = None
                    stats["last_verified_at"] = verified_at
                    stats["last_deferred_reason"] = None
                    stats["last_sample_at"] = verified_at
                    stats["last_source"] = source
                    stats["last_cache_ages_seconds"] = ages
                    stats["last_errors"] = deepcopy(status.get("errors", []))
                    stats["last_violations"] = deepcopy(violations)

                self._update_runtime(
                    pair_id,
                    monitor_state="healthy",
                    monitor_verification_deferred=False,
                    monitor_unverified_since=None,
                    monitor_unverified_seconds=0.0,
                    monitor_last_warning=None,
                    monitor_last_verified_at=verified_at,
                    monitor_last_sample_at=verified_at,
                )

                if violations:
                    self.store.event(
                        "runtime_monitor",
                        f"{pair_id} runtime safety violation",
                        asset_id=pair.pcs_asset_id,
                        payload={
                            "pair_id": pair_id,
                            "violations": violations,
                            "source": source,
                        },
                    )
                    stop = self._safe_stop_internal(
                        username,
                        pair,
                        open_bms=True,
                        reason=f"runtime_monitor_violation: {violations}",
                    )
                    with self._lock:
                        self._runtime_monitor_stats[pair_id]["safety_stops"] += 1
                    self._update_runtime(
                        pair_id,
                        stage="runtime_safety_stop",
                        last_action="runtime_monitor",
                        last_error=violations,
                        run_status="failed",
                        completed_at=now_iso(),
                        runtime_safety_stop=stop,
                        monitor_state="failed_safety_violation",
                    )
                    return
                if stop_event.wait(self.config.runtime_monitor_interval_seconds):
                    break
        except Exception as error:
            # Unexpected software failures remain fail-safe. Scheduler contention
            # and transient live-read failures are handled above as deferred
            # verification and do not arrive here.
            LOGGER.exception("Runtime monitor failed pair=%s", pair_id)
            try:
                stop = self._safe_stop_internal(
                    username,
                    pair,
                    open_bms=True,
                    reason=f"runtime_monitor_exception: {error}",
                )
            except Exception as stop_error:
                stop = {"ok": False, "error": str(stop_error)}
            with self._lock:
                stats = self._runtime_monitor_stats[pair_id]
                stats["last_sample_at"] = now_iso()
                stats["last_error"] = str(error)
                stats["safety_stops"] += 1
            self._update_runtime(
                pair_id,
                stage="runtime_monitor_failed",
                last_action="runtime_monitor",
                last_error=str(error),
                run_status="failed",
                completed_at=now_iso(),
                runtime_safety_stop=stop,
                monitor_state="failed_exception",
            )
        finally:
            self._update_runtime(
                pair_id,
                monitor_active=False,
                monitor_stop_requested=False,
            )


    def capabilities(self) -> dict[str, Any]:
        return {
            "controller": "field_validated_bms_pcs_sequence_controller",
            "version": "2.6.0-multi-pair",
            "enabled": self.config.enabled,
            "full_automatic_sequence_allowed": self.config.allow_full_automatic_sequence,
            "pairs": [pair.model_dump() for pair in self.config.pairs],
            "modes": {
                "commissioning_next_step": True,
                "automatic_start": self.config.allow_full_automatic_sequence,
                "runtime_monitor": self.config.runtime_monitor_enabled,
                "safe_stop_monitor_quiesce": True,
                "parallel_pair_operation": True,
                "runtime_refresh_contention_is_deferred": True,
                "fair_fifo_live_refresh_lane": True,
                "all_pair_cache_overview": True,
            },
            "validated_sequence": [
                "PCS stopped, Remote/PQ/constant-power, 0 kW",
                "Use selected rack BCU 0x0402=1; do not write BAU 0x3005-0x3008",
                "Leave BMS insulation command 0x0401 at 0",
                "Start BMS precharge 0x0402=1",
                "Verify precharge state 3 and both main contactors closed",
                "Verify rack voltage is present at PCS battery input",
                "Start PCS 0x1400=0xFF00 at 0 kW",
                "Verify PCS soft-start/self-test, DC breaker closed and DC bus matched",
                "Apply +kW for discharge or -kW for charge within BMS limits",
            ],
            "safety_limits": {
                "bms_rack_voltage_v": [self.config.bms_rack_voltage_min_v, self.config.bms_rack_voltage_max_v],
                "pcs_dc_bus_voltage_v": [self.config.pcs_dc_bus_voltage_min_v, self.config.pcs_dc_bus_voltage_max_v],
                "max_abs_power_kw": self.config.max_abs_power_kw,
                "positive_power_means": "discharge",
                "negative_power_means": "charge",
                "ready_voltage_match_tolerance_v": self.config.ready_voltage_match_tolerance_v,
                "automatic_power_ramp_step_kw": self.config.automatic_power_ramp_step_kw,
                "automatic_power_ramp_interval_seconds": self.config.automatic_power_ramp_interval_seconds,
                "validation_dc_bus_threshold_v": self.config.validation_dc_bus_threshold_v,
                "runtime_monitor_refresh_wait_seconds": self.config.runtime_monitor_refresh_wait_seconds,
                "runtime_monitor_max_unverified_seconds": self.config.runtime_monitor_max_unverified_seconds,
            },
            "bms_registers": {
                "rack_enable_control": "Not used in normal EMS runtime; vendor instructed no writes to BAU 0x3005-0x3008",
                "individual_rack_runtime_control": "Selected BCU 0x0402, 1=start precharge/connect, 0=stop/open",
                "bau_rack_enable_feedback": "BAU 0x102A retained for diagnostics only; not a pair-level runtime gate",
                "global_direction_summary": "BAU 0x1001 full/empty bits are diagnostic for individual-pair control; enforce selected-rack current limits and detailed fault words",
                "insulation_sampling": "BCU 0x0401 is BMS-internal; manual EMS writes disabled per vendor confirmation",
                "precharge_control": "BCU 0x0402, 1=start, 0=stop/open main positive",
                "fault_recovery": "BAU 0x3047, write 1 only; only while PCS stopped, rack disabled and contactors open",
                "rack_voltage": "BCU 0x0231, S16, 0.1 V",
                "precharge_state": "BCU 0x0018, 3=success",
                "contactor_state": "BCU 0x001F, bit0 positive, bit2 negative",
                "charge_current_limit": "BCU 0x0225, U16, 0.1 A",
                "discharge_current_limit": "BCU 0x0226, U16, 0.1 A",
            },
            "pcs_registers": {
                "dc_bus_voltage": "0x1100, S16, 0.1 V",
                "battery_input_voltage": "0x1102, S16, 0.1 V",
                "operating_state": "0x1200 bitfield: 1=Stop, 2=SoftStart, 4=SelfTest, 8=Standby, bit4=Running; combined values such as 80 are valid",
                "status_word_1": "0x1201: bit0 Remote feedback, bit1 Authorization",
                "status_word_2": "0x1202: bit6 DC breaker state, 0=closed/1=open",
                "input_fault_word": "0x1210: bit7 DC breaker feedback, 0=open/1=closed",
                "system_fault_ext3": "0x121A: bit2 DC soft-start fault, bit3 DC soft-start relay fault",
                "remote_on_off": "0x1400, 0xFF00=start, 0x00FF=stop",
                "remote_local_mode": "0x1402, 0x00FF=remote",
                "product_run_mode": "0x1406, 1=PQ",
                "pq_work_mode": "0x1407, 0=constant power",
                "active_power_setpoint": "0x1409, S16, 0.1 kW, +discharge/-charge",
                "actual_active_power": "0x110D, S16, 0.1 kW",
            },
            "confirmation_phrase": self.config.confirmation_phrase,
            "automatic_confirmation_phrase": self.config.automatic_confirmation_phrase,
            "api_endpoints": {
                "status": "GET /api/control-sequence/{pair_id}/status?fresh=false",
                "all_pair_status": "GET /api/control-sequence/status/all",
                "next_step": "POST /api/control-sequence/{pair_id}/next-step",
                "automatic_start": "POST /api/control-sequence/{pair_id}/automatic-start",
                "set_power": "POST /api/control-sequence/{pair_id}/set-power",
                "zero_power": "POST /api/control-sequence/{pair_id}/zero-power",
                "safe_stop": "POST /api/control-sequence/{pair_id}/safe-stop",
                "abort": "POST /api/control-sequence/{pair_id}/abort",
            },
        }
