from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from app.assets.bms_driver import BmsModbusDriver
from app.assets.elecod_adapter import ElecodPcsAdapter
from app.assets.lineage_adapter import LineageBmsAdapter, LINEAGE_STATE_LABELS
from app.assets.normalized import BatteryRackState, PcsState
from app.assets.pcs_driver import PcsModbusDriver
from app.core.config import ControlPairConfig, GatewayConfig, PcsDeviceConfig
from app.services.bms_pcs_control import ControlStatusBusyError
from app.services.normalized_views import elecod_pcs_view, lineage_rack_view, lineage_system_view
from app.storage.sqlite_store import SQLiteStore

LOGGER = logging.getLogger(__name__)
Direction = Literal["charge", "discharge"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VendorNeutralPairControlService:
    """Vendor-neutral 4-pair control engine for the frozen Ornate gateway architecture.

    This service preserves the public Kinetics control-sequence API while moving
    vendor-specific register semantics into adapters.  It is currently selected
    for the Lineage BMS + Elecod PCS combination; the field-validated legacy
    Kinetics controller remains untouched and is selected for Kinetics assets.

    Important source-grounded limitation: Lineage V05 does not expose a normal
    EMS precharge command/success point.  The engine therefore treats battery
    preparation as an observable state (main contactors + rack voltage) and waits
    for the vendor-approved BMS automatic sequence.  It never substitutes forced
    contactor-close commands for missing precharge semantics.
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
        self.config = gateway_config.control_sequence
        self.bms_driver = bms_driver
        self.pcs_driver = pcs_driver
        self.store = store
        self._snapshot_provider = snapshot_provider
        self._lock = threading.RLock()

        self.battery = LineageBmsAdapter(
            bms_driver,
            allow_forced_contactor_control=self.config.allow_forced_bms_disconnect,
            allow_warning_operation=self.config.allow_bms_warning_operation,
        )
        self._pcs_adapters: dict[str, ElecodPcsAdapter] = {}
        for device in gateway_config.pcs.devices:
            rated = device.rated_power_kw
            if rated is None:
                raise ValueError(
                    f"Elecod device {device.asset_id} requires rated_power_kw for normalized kW control"
                )
            self._pcs_adapters[device.asset_id] = ElecodPcsAdapter(
                pcs_driver,
                rated_power_kw=rated,
                power_sign_validated=gateway_config.pcs.power_sign_validated,
                positive_power_is_discharge=gateway_config.pcs.positive_power_is_discharge,
            )

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
                "abort_requested": False,
            }
            for pair in self.config.pairs
        }
        self._abort_events = {pair.pair_id: threading.Event() for pair in self.config.pairs}
        self._monitor_stop_events = {pair.pair_id: threading.Event() for pair in self.config.pairs}
        self._monitor_threads: dict[str, threading.Thread] = {}
        self._safe_stop_locks = {pair.pair_id: threading.RLock() for pair in self.config.pairs}
        self._sequence_executor = ThreadPoolExecutor(
            max_workers=self.config.automatic_executor_workers,
            thread_name_prefix="vendor-neutral-control",
        )
        self._sequence_futures: dict[str, Future[None]] = {}
        # Preserve the Kinetics operational rule: only one heavy startup/ramp is
        # admitted at once, while already-running pairs remain independently monitored.
        self._startup_lock = threading.Lock()
        self._runtime_monitor_stats = {
            pair.pair_id: {
                "samples": 0,
                "verified_samples": 0,
                "unverified_samples": 0,
                "safety_stops": 0,
                "last_sample_at": None,
                "last_errors": [],
                "last_violations": [],
            }
            for pair in self.config.pairs
        }

    # ------------------------------------------------------------------
    # Common helpers
    # ------------------------------------------------------------------
    def _pair(self, pair_id: str) -> ControlPairConfig:
        pair = next((item for item in self.config.pairs if item.pair_id == pair_id), None)
        if pair is None:
            raise KeyError(f"Unknown control pair: {pair_id}")
        if not pair.enabled:
            raise PermissionError(f"Control pair {pair_id} is disabled")
        return pair

    def _device(self, asset_id: str) -> PcsDeviceConfig:
        return self.pcs_driver.device(asset_id)

    def _pcs(self, asset_id: str) -> ElecodPcsAdapter:
        try:
            return self._pcs_adapters[asset_id]
        except KeyError as error:
            raise KeyError(f"No normalized PCS adapter for {asset_id}") from error

    def _require_confirmation(self, confirmation: str) -> None:
        if confirmation != self.config.confirmation_phrase:
            raise PermissionError(
                f"Hardware write confirmation must equal {self.config.confirmation_phrase!r}"
            )

    def _require_write_gates(self, confirmation: str) -> None:
        self._require_confirmation(confirmation)
        if not self.config.enabled:
            raise PermissionError("Staged BMS/PCS control is disabled in configuration")
        if self.gateway_config.mode not in {"control_enabled", "mock"}:
            raise PermissionError("Gateway mode must be control_enabled (or mock for software-in-loop) for staged writes")
        if not self.gateway_config.bms.write_enabled:
            raise PermissionError("BMS writes are disabled")
        if not self.gateway_config.pcs.write_enabled:
            raise PermissionError("PCS writes are disabled")
        # Real Lineage+Elecod hardware control remains positively locked until
        # the protocol semantics that cannot be proven from the supplied sheets
        # have been confirmed on the actual BESS.  SIL/mock mode intentionally
        # bypasses these field-validation gates so the complete state machine can
        # be regression-tested before hardware arrives.
        if self.gateway_config.mode != "mock":
            missing: list[str] = []
            bms = self.gateway_config.bms
            pcs = self.gateway_config.pcs
            for field, label in (
                (bms.addressing_validated, "Lineage register addressing"),
                (bms.float_word_order_validated, "Lineage FLOAT word order"),
                (bms.current_sign_validated, "Lineage current sign"),
                (bms.automatic_precharge_validated, "Lineage automatic precharge/readiness sequence"),
                (pcs.addressing_validated, "Elecod register addressing"),
                (pcs.start_stop_validated, "Elecod start/stop write semantics"),
                (pcs.ready_status_validated, "Elecod readiness/status interpretation"),
            ):
                if not field:
                    missing.append(label)
            if missing:
                raise PermissionError(
                    "Field validation gates are incomplete: " + "; ".join(missing)
                )

    def _require_automatic_gates(self, confirmation: str) -> None:
        if confirmation != self.config.automatic_confirmation_phrase:
            raise PermissionError(
                f"Automatic sequence confirmation must equal {self.config.automatic_confirmation_phrase!r}"
            )
        if not self.config.allow_full_automatic_sequence:
            raise PermissionError("Full automatic sequence is disabled in configuration")
        # Automatic control still requires all normal write gates.
        self._require_write_gates(self.config.confirmation_phrase)

    def _update_runtime(self, pair_id: str, **changes: Any) -> None:
        with self._lock:
            self._runtime[pair_id].update(changes)
            self._runtime[pair_id]["last_updated_at"] = now_iso()

    def _runtime_snapshot(self, pair_id: str) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._runtime[pair_id])

    def _audit(
        self,
        username: str,
        pair: ControlPairConfig,
        action: str,
        requested: Any,
        response: dict[str, Any],
        status: str = "success",
    ) -> None:
        self.store.audit_command(
            username,
            pair.pcs_asset_id,
            f"pair_control:{action}",
            requested,
            status,
            response,
        )
        self.store.event(
            "control_sequence",
            f"Vendor-neutral pair stage {action} {status}",
            asset_id=pair.pcs_asset_id,
            payload={"pair_id": pair.pair_id, **response},
        )

    @staticmethod
    def _voltage_valid(value: float | None, minimum: float, maximum: float) -> bool:
        return value is not None and minimum <= float(value) <= maximum

    def _voltages_match(self, first: float | None, second: float | None) -> bool:
        if first is None or second is None:
            return False
        return abs(float(first) - float(second)) <= self.config.ready_voltage_match_tolerance_v

    def _cached_pair(self, pair: ControlPairConfig) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        if self._snapshot_provider is None:
            raise RuntimeError("Cached pair snapshot provider is unavailable")
        snapshot = self._snapshot_provider(pair.rack_id, pair.pcs_asset_id)
        rack = lineage_rack_view(snapshot["rack"])
        pcs = elecod_pcs_view(snapshot["pcs"])
        system = lineage_system_view(snapshot.get("bank") or {})
        return rack, pcs, system

    def _live_pair(self, pair: ControlPairConfig) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, str]]]:
        errors: list[dict[str, str]] = []
        try:
            rack_state = self.battery.rack_state(pair.rack_id)
            rack = asdict(rack_state)
        except Exception as error:
            rack = {"rack_id": pair.rack_id, "online": False, "blocking_reasons": ["read_failed"]}
            errors.append({"target": "bms_rack", "error": str(error)})
        try:
            pcs_state = self._pcs(pair.pcs_asset_id).state(pair.pcs_asset_id)
            pcs = asdict(pcs_state)
            # Convert adapter names to the normalized view names used below.
            pcs.update(
                {
                    "active_power_kw": pcs_state.actual_active_power_kw,
                    "reactive_power_kvar": pcs_state.actual_reactive_power_kvar,
                }
            )
        except Exception as error:
            pcs = {"asset_id": pair.pcs_asset_id, "online": False}
            errors.append({"target": "pcs", "error": str(error)})

        system: dict[str, Any] = {}
        keys = (
            "battery_system_state",
            "system_max_charge_power",
            "system_max_discharge_power",
            "system_max_charge_current",
            "system_max_discharge_current",
            "system_soc",
            "system_soh",
        )
        for key in keys:
            try:
                point = self.bms_driver.read_point("bms_bank", key)
                system[key] = point.get("value")
            except Exception as error:
                errors.append({"target": f"bms_bank:{key}", "error": str(error)})
        system = {
            "state_code": int(system["battery_system_state"]) if system.get("battery_system_state") is not None else None,
            "state": LINEAGE_STATE_LABELS.get(int(system["battery_system_state"])) if system.get("battery_system_state") is not None else None,
            "max_charge_power_kw": system.get("system_max_charge_power"),
            "max_discharge_power_kw": system.get("system_max_discharge_power"),
            "max_charge_current_a": system.get("system_max_charge_current"),
            "max_discharge_current_a": system.get("system_max_discharge_current"),
            "soc_percent": system.get("system_soc"),
            "soh_percent": system.get("system_soh"),
        }
        return rack, pcs, system, errors

    def _build_status(
        self,
        pair: ControlPairConfig,
        rack: dict[str, Any],
        pcs: dict[str, Any],
        system: dict[str, Any],
        errors: list[dict[str, str]],
        *,
        source: str,
    ) -> dict[str, Any]:
        rack_voltage = rack.get("voltage_v")
        pcs_dc_voltage = pcs.get("dc_voltage_v")
        pcs_dc_bus = pcs.get("dc_bus_voltage_v")
        contactors_ready = bool(rack.get("positive_contactor_closed")) and bool(
            rack.get("negative_contactor_closed")
        )
        battery_ready = contactors_ready and self._voltage_valid(
            rack_voltage,
            self.config.bms_rack_voltage_min_v,
            self.config.bms_rack_voltage_max_v,
        )
        input_match = self._voltages_match(rack_voltage, pcs_dc_voltage)
        bus_valid = self._voltage_valid(
            pcs_dc_bus,
            self.config.pcs_dc_bus_voltage_min_v,
            self.config.pcs_dc_bus_voltage_max_v,
        )
        bus_match = self._voltages_match(pcs_dc_voltage, pcs_dc_bus)
        pcs_running = pcs.get("running") is True
        pcs_faulted = pcs.get("faulted") is True
        pcs_online = bool(pcs.get("online"))
        rack_online = bool(rack.get("online"))

        # Elecod status bit 12 is EPO.  The normalized phase-4 view does not
        # expose it yet, so live adapter raw_status is decoded here when present.
        raw_status = pcs.get("raw_status")
        pcs_epo = pcs.get("epo") is True
        if raw_status is not None:
            pcs_epo = pcs_epo or bool((int(raw_status) >> 12) & 1)

        hard_blocked = (
            not rack_online
            or not pcs_online
            or pcs_faulted
            or pcs_epo
            or rack.get("state_code") == 0xAAAA
        )
        summary = {
            "rack_id": pair.rack_id,
            "pcs_asset_id": pair.pcs_asset_id,
            "rack_state": rack.get("state"),
            "rack_state_code": rack.get("state_code"),
            "rack_operating_state": rack.get("operating_state") or rack.get("operating_state_label"),
            "rack_voltage_v": rack_voltage,
            "rack_current_a": rack.get("current_a"),
            "rack_soc_percent": rack.get("soc_percent"),
            "rack_soh_percent": rack.get("soh_percent"),
            "rack_charge_current_limit_a": rack.get("max_charge_current_a"),
            "rack_discharge_current_limit_a": rack.get("max_discharge_current_a"),
            "bms_charge_power_limit_kw": rack.get("max_charge_power_kw"),
            "bms_discharge_power_limit_kw": rack.get("max_discharge_power_kw"),
            "system_charge_power_limit_kw": system.get("max_charge_power_kw"),
            "system_discharge_power_limit_kw": system.get("max_discharge_power_kw"),
            "positive_contactor_closed": rack.get("positive_contactor_closed"),
            "negative_contactor_closed": rack.get("negative_contactor_closed"),
            "contactors_ready": contactors_ready,
            "battery_ready": battery_ready,
            # Compatibility alias only. Lineage V05 does not expose an explicit
            # precharge-success register; this means the observable DC path is ready.
            "precharge_success": battery_ready,
            "precharge_semantics": "lineage_v05_compatibility_alias_from_main_contactor_readiness",
            "positive_insulation_mohm": rack.get("positive_insulation_mohm"),
            "negative_insulation_mohm": rack.get("negative_insulation_mohm"),
            "rack_voltage_valid": self._voltage_valid(
                rack_voltage,
                self.config.bms_rack_voltage_min_v,
                self.config.bms_rack_voltage_max_v,
            ),
            "pcs_running": pcs_running,
            "pcs_faulted": pcs_faulted,
            "pcs_standby": pcs.get("standby"),
            "pcs_shutdown": pcs.get("shutdown"),
            "pcs_off_grid": pcs.get("off_grid"),
            "pcs_dc_relay_feedback_closed": pcs.get("dc_relay_connected"),
            "pcs_ac_relay_feedback_closed": pcs.get("ac_relay_connected"),
            "pcs_dc_precharge_connected": pcs.get("dc_precharge_connected"),
            "pcs_actual_power_kw": pcs.get("active_power_kw") if "active_power_kw" in pcs else pcs.get("actual_active_power_kw"),
            "pcs_actual_reactive_power_kvar": pcs.get("reactive_power_kvar") if "reactive_power_kvar" in pcs else pcs.get("actual_reactive_power_kvar"),
            "pcs_battery_voltage_v": pcs_dc_voltage,
            "pcs_dc_bus_voltage_v": pcs_dc_bus,
            "pcs_dc_current_a": pcs.get("dc_current_a"),
            "pcs_dc_bus_valid": bus_valid,
            "rack_and_pcs_input_match": input_match,
            "pcs_input_and_dc_bus_match": bus_match,
            "pcs_ready_state": pcs_running and not pcs_faulted,
            "pcs_fault_shutdown": pcs_faulted,
            "pcs_epo": pcs_epo,
            "charge_allowed": bool(rack.get("charge_allowed")),
            "discharge_allowed": bool(rack.get("discharge_allowed")),
            "blockers": {
                "system_charge_prohibited": not bool(rack.get("charge_allowed")),
                "system_discharge_prohibited": not bool(rack.get("discharge_allowed")),
                "system_fault": rack.get("state_code") == 0xAAAA,
                "emergency_stop_fault": pcs_epo,
                "documented_critical_fault": rack.get("state_code") == 0xAAAA or pcs_faulted,
                "direction_permission_source": "lineage_rack_state_and_dynamic_limits",
            },
        }
        workflow = {
            "hard_blocked": hard_blocked,
            "battery_ready": battery_ready,
            "pcs_ready": pcs_running and not pcs_faulted,
            "power_control_ready": (
                battery_ready
                and pcs_running
                and not pcs_faulted
                and (not self.config.require_pcs_dc_relay_for_ready or pcs.get("dc_relay_connected") is True)
                and (not self.config.require_pcs_ac_relay_for_ready or pcs.get("ac_relay_connected") is True)
                and (not self.config.require_voltage_match_for_ready or (input_match and bus_match))
            ),
            "next_action": (
                "clear_faults"
                if hard_blocked
                else "wait_for_bms_automatic_precharge"
                if not battery_ready
                else "start_pcs"
                if not pcs_running
                else "set_power"
            ),
        }
        return {
            "pair": pair.model_dump(),
            "runtime": self._runtime_snapshot(pair.pair_id),
            "summary": summary,
            "workflow": workflow,
            "write_gates": {
                "mode_control_enabled": self.gateway_config.mode in {"control_enabled", "mock"},
                "control_sequence_enabled": self.config.enabled,
                "bms_write_enabled": self.gateway_config.bms.write_enabled,
                "pcs_write_enabled": self.gateway_config.pcs.write_enabled,
                "automatic_sequence_enabled": self.config.allow_full_automatic_sequence,
                "elecod_power_sign_validated": self.gateway_config.pcs.power_sign_validated,
                "forced_bms_disconnect_enabled": self.config.allow_forced_bms_disconnect,
            },
            "errors": errors,
            "refresh": {"source": source, "timestamp": now_iso()},
            "battery_system": system,
        }

    # ------------------------------------------------------------------
    # Read/status API
    # ------------------------------------------------------------------
    def status(
        self,
        pair_id: str,
        *,
        fresh: bool = False,
        wait_for_refresh: bool = True,
        return_cached_if_busy: bool = False,
    ) -> dict[str, Any]:
        del wait_for_refresh, return_cached_if_busy  # interface compatibility
        pair = self._pair(pair_id)
        if fresh:
            rack, pcs, system, errors = self._live_pair(pair)
            return self._build_status(pair, rack, pcs, system, errors, source="live_fieldbus")
        try:
            rack, pcs, system = self._cached_pair(pair)
            return self._build_status(pair, rack, pcs, system, [], source="background_poll_cache")
        except Exception as error:
            # Keep read APIs usable during startup before the first cache fill.
            return self._build_status(
                pair,
                {"rack_id": pair.rack_id, "online": False, "blocking_reasons": ["cache_unavailable"]},
                {"asset_id": pair.pcs_asset_id, "online": False},
                {},
                [{"target": "cache", "error": str(error)}],
                source="cache_unavailable",
            )

    def all_pair_status(self) -> dict[str, Any]:
        pairs: dict[str, Any] = {}
        active_pairs: list[str] = []
        starting_pairs: list[str] = []
        for pair in self.config.pairs:
            if not pair.enabled:
                continue
            item = self.status(pair.pair_id, fresh=False)
            pairs[pair.pair_id] = item
            runtime = item["runtime"]
            if abs(float(runtime.get("commanded_power_kw") or 0.0)) > 1e-9:
                active_pairs.append(pair.pair_id)
            if runtime.get("run_status") in {"queued", "running"}:
                starting_pairs.append(pair.pair_id)
        return {
            "pairs": pairs,
            "count": len(pairs),
            "summary": {
                "parallel_operation_supported": True,
                "active_pairs": active_pairs,
                "starting_pairs": starting_pairs,
                "startup_policy": "single_heavy_startup_lane_parallel_runtime_monitoring",
            },
            "timestamp": now_iso(),
        }

    @staticmethod
    def _compact_pair_status(item: dict[str, Any]) -> dict[str, Any]:
        summary = item.get("summary", {})
        runtime = item.get("runtime", {})
        return {
            "pair_id": item.get("pair", {}).get("pair_id"),
            "stage": runtime.get("stage"),
            "run_status": runtime.get("run_status"),
            "direction": runtime.get("requested_direction"),
            "requested_power_kw": runtime.get("requested_power_kw"),
            "commanded_power_kw": runtime.get("commanded_power_kw"),
            "rack_voltage_v": summary.get("rack_voltage_v"),
            "rack_soc_percent": summary.get("rack_soc_percent"),
            "battery_ready": summary.get("battery_ready"),
            "pcs_running": summary.get("pcs_running"),
            "pcs_actual_power_kw": summary.get("pcs_actual_power_kw"),
            "hard_blocked": item.get("workflow", {}).get("hard_blocked"),
            "errors": item.get("errors", []),
        }

    def all_pair_status_compact(self) -> dict[str, Any]:
        full = self.all_pair_status()
        return {
            "pairs": {key: self._compact_pair_status(value) for key, value in full["pairs"].items()},
            "count": full["count"],
            "summary": full["summary"],
            "timestamp": full["timestamp"],
        }

    def refresh_diagnostics(self) -> dict[str, Any]:
        return {
            "controller": "vendor_neutral",
            "live_status_policy": "direct_control_reads_only_when_fresh=true_or_during_control",
            "background_cache_used_for_normal_status": True,
            "timestamp": now_iso(),
        }

    def runtime_monitor_diagnostics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.config.runtime_monitor_enabled,
                "pairs": deepcopy(self._runtime_monitor_stats),
                "timestamp": now_iso(),
            }

    def runtime_monitor_sample(self, pair_id: str) -> dict[str, Any]:
        pair = self._pair(pair_id)
        return self._runtime_monitor_status(pair)

    # ------------------------------------------------------------------
    # Readiness and safety calculations
    # ------------------------------------------------------------------
    def _rated_power_kw(self, pair: ControlPairConfig) -> float:
        device = self._device(pair.pcs_asset_id)
        return float(device.rated_power_kw or self.config.max_abs_power_kw)

    def _other_direction_commanded_kw(self, pair_id: str, direction: Direction) -> float:
        total = 0.0
        with self._lock:
            for other_id, runtime in self._runtime.items():
                if other_id == pair_id:
                    continue
                value = float(runtime.get("commanded_power_kw") or 0.0)
                if direction == "charge" and value < 0:
                    total += abs(value)
                if direction == "discharge" and value > 0:
                    total += value
        return total

    def precheck(self, pair_id: str, direction: Direction, requested_power_kw: float) -> dict[str, Any]:
        if direction not in {"charge", "discharge"}:
            raise ValueError("Direction must be charge or discharge")
        pair = self._pair(pair_id)
        requested = float(requested_power_kw)
        status = self.status(pair_id, fresh=True)
        summary = status["summary"]
        system = status.get("battery_system", {})
        current_limit = (
            summary.get("rack_charge_current_limit_a")
            if direction == "charge"
            else summary.get("rack_discharge_current_limit_a")
        )
        rack_power_limit = (
            summary.get("bms_charge_power_limit_kw")
            if direction == "charge"
            else summary.get("bms_discharge_power_limit_kw")
        )
        system_power_limit = (
            system.get("max_charge_power_kw") if direction == "charge" else system.get("max_discharge_power_kw")
        )
        permission = summary.get("charge_allowed") if direction == "charge" else summary.get("discharge_allowed")
        project_limit = min(self.config.max_abs_power_kw, self._rated_power_kw(pair))
        dynamic_limit = project_limit
        if rack_power_limit is not None:
            dynamic_limit = min(dynamic_limit, max(0.0, float(rack_power_limit)))
        system_budget = None
        if system_power_limit is not None:
            system_budget = max(
                0.0,
                float(system_power_limit) - self._other_direction_commanded_kw(pair_id, direction),
            )
            dynamic_limit = min(dynamic_limit, system_budget)

        checks = {
            "all_required_reads_ok": not status["errors"],
            "rack_voltage_valid": bool(summary.get("rack_voltage_valid")),
            "battery_contactors_ready": bool(summary.get("contactors_ready")),
            "pcs_online": bool(status["workflow"].get("pcs_ready") or summary.get("pcs_running")),
            "pcs_running": bool(summary.get("pcs_running")),
            "pcs_not_faulted": not bool(summary.get("pcs_faulted")),
            "pcs_dc_bus_valid": bool(summary.get("pcs_dc_bus_valid")),
            "pcs_dc_relay_ready": (
                True
                if not self.config.require_pcs_dc_relay_for_ready
                else summary.get("pcs_dc_relay_feedback_closed") is True
            ),
            "pcs_ac_relay_ready": (
                True
                if not self.config.require_pcs_ac_relay_for_ready
                else summary.get("pcs_ac_relay_feedback_closed") is True
            ),
            "voltage_match_ready": (
                True
                if not self.config.require_voltage_match_for_ready
                else bool(summary.get("rack_and_pcs_input_match"))
                and bool(summary.get("pcs_input_and_dc_bus_match"))
            ),
            "bms_direction_allowed": bool(permission),
            "bms_current_limit_available": current_limit is not None
            and float(current_limit) >= self.config.minimum_bms_current_limit_a,
            "requested_power_non_negative": requested >= 0.0,
            "requested_power_within_project_limit": requested <= project_limit + 1e-9,
            "requested_power_within_dynamic_bms_limit": (
                True
                if not self.config.enforce_dynamic_bms_power_limit
                else requested <= dynamic_limit + 1e-9
            ),
            "elecod_power_sign_validated": (
                True
                if not self.config.require_power_sign_validation
                else self.gateway_config.pcs.power_sign_validated
            ),
        }
        result = {
            "ok": all(checks.values()),
            "pair": pair.model_dump(),
            "direction": direction,
            "requested_power_kw": requested,
            "effective_power_limit_kw": round(dynamic_limit, 3),
            "limit_breakdown": {
                "gateway_project_limit_kw": project_limit,
                "rack_dynamic_limit_kw": rack_power_limit,
                "system_dynamic_limit_kw": system_power_limit,
                "system_remaining_budget_kw": system_budget,
                "other_pairs_same_direction_commanded_kw": self._other_direction_commanded_kw(pair_id, direction),
            },
            "checks": checks,
            "status": status,
            "timestamp": now_iso(),
        }
        self._update_runtime(
            pair_id,
            stage="precheck_passed" if result["ok"] else "precheck_failed",
            last_action="precheck",
            last_error=None if result["ok"] else [key for key, ok in checks.items() if not ok],
            requested_direction=direction,
            requested_power_kw=requested,
        )
        return result

    # ------------------------------------------------------------------
    # Staged/manual control API
    # ------------------------------------------------------------------
    def enable_rack(
        self,
        username: str,
        pair_id: str,
        direction: Direction,
        requested_power_kw: float,
        confirmation: str,
    ) -> dict[str, Any]:
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        # Lineage V05 has no normal rack-enable command. Keep API compatibility
        # and expose the actual semantic difference instead of inventing a write.
        state = self.battery.rack_state(pair.rack_id)
        response = {
            "ok": state.online and state.state_code != 0xAAAA,
            "stage": "rack_enable_not_applicable_bms_automatic",
            "command_issued": False,
            "direction": direction,
            "requested_power_kw": requested_power_kw,
            "rack": asdict(state),
            "note": "Lineage V05 exposes no normal EMS rack-enable command; BMS automatic control remains authoritative.",
        }
        self._update_runtime(pair_id, stage=response["stage"], last_action="enable_rack")
        self._audit(username, pair, "enable_rack", {"direction": direction, "power_kw": requested_power_kw}, response)
        return response

    def verify_insulation(self, pair_id: str) -> dict[str, Any]:
        pair = self._pair(pair_id)
        state = self.battery.rack_state(pair.rack_id)
        measurements_available = (
            state.positive_insulation_mohm is not None and state.negative_insulation_mohm is not None
        )
        return {
            "ok": state.online and measurements_available and state.state_code != 0xAAAA,
            "pair": pair.model_dump(),
            "positive_insulation_mohm": state.positive_insulation_mohm,
            "negative_insulation_mohm": state.negative_insulation_mohm,
            "threshold_validated": False,
            "note": "Lineage V05 provides insulation measurements but does not define the EMS acceptance threshold in this protocol sheet.",
            "timestamp": now_iso(),
        }

    def start_insulation(self, username: str, pair_id: str, confirmation: str) -> dict[str, Any]:
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        result = self.verify_insulation(pair_id)
        response = {
            **result,
            "stage": "insulation_automatic_observation",
            "command_issued": False,
            "note": "No Lineage V05 EMS command for insulation sampling is defined; measurements are observed from BMS telemetry.",
        }
        self._update_runtime(pair_id, stage=response["stage"], last_action="start_insulation")
        self._audit(username, pair, "start_insulation", None, response)
        return response

    def start_precharge(self, username: str, pair_id: str, confirmation: str) -> dict[str, Any]:
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        result = self.battery.prepare_for_operation(pair.rack_id)
        response = {
            "ok": result.ok,
            "stage": result.state,
            "command_issued": result.command_issued,
            "message": result.message,
            "details": result.details,
            "precharge_semantics": "lineage_v05_bms_automatic_observation",
        }
        self._update_runtime(
            pair_id,
            stage=result.state,
            last_action="start_precharge",
            last_error=None if result.ok else result.message,
        )
        self._audit(username, pair, "start_precharge", None, response, "success" if result.ok else "pending")
        return response

    def recover_bms(self, username: str, pair_id: str, confirmation: str) -> dict[str, Any]:
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        before = self.battery.rack_state(pair.rack_id)
        if before.positive_contactor_closed or before.negative_contactor_closed:
            raise ValueError("BMS fault reset is blocked while a main battery contactor is closed")
        action = self.battery.fault_reset()
        time.sleep(min(1.0, self.config.sample_interval_seconds))
        after = self.battery.rack_state(pair.rack_id)
        response = {
            "ok": after.state_code != 0xAAAA,
            "stage": "bms_recovered" if after.state_code != 0xAAAA else "bms_fault_still_active",
            "action": action,
            "before": asdict(before),
            "after": asdict(after),
            "fault_cleared": after.state_code != 0xAAAA,
        }
        self._update_runtime(pair_id, stage=response["stage"], last_action="recover_bms")
        self._audit(username, pair, "recover_bms", 1, response, "success" if response["ok"] else "failed")
        return response

    def verify_ready(self, pair_id: str) -> dict[str, Any]:
        pair = self._pair(pair_id)
        status = self.status(pair_id, fresh=True)
        s = status["summary"]
        checks = {
            "battery_ready": bool(s.get("battery_ready")),
            "rack_and_pcs_input_voltage_match": (
                True
                if not self.config.require_voltage_match_for_ready
                else bool(s.get("rack_and_pcs_input_match"))
            ),
            "pcs_not_faulted": not bool(s.get("pcs_faulted")),
            "pcs_epo_clear": not bool(s.get("pcs_epo")),
        }
        # Before PCS start, the internal bus/DC relay may legitimately be open.
        # After start, add the stricter running-state checks.
        if s.get("pcs_running"):
            checks["pcs_dc_bus_valid"] = bool(s.get("pcs_dc_bus_valid"))
            checks["pcs_input_and_dc_bus_match"] = (
                True
                if not self.config.require_voltage_match_for_ready
                else bool(s.get("pcs_input_and_dc_bus_match"))
            )
            if self.config.require_pcs_dc_relay_for_ready:
                checks["pcs_dc_relay_ready"] = s.get("pcs_dc_relay_feedback_closed") is True
            if self.config.require_pcs_ac_relay_for_ready:
                checks["pcs_ac_relay_ready"] = s.get("pcs_ac_relay_feedback_closed") is True
        return {
            "ok": all(checks.values()) and not status["errors"],
            "pair": pair.model_dump(),
            "checks": checks,
            "status": status,
            "timestamp": now_iso(),
        }

    def prepare_pcs_standby(self, username: str, pair_id: str, confirmation: str) -> dict[str, Any]:
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        pcs = self._pcs(pair.pcs_asset_id)
        zero = pcs.set_zero_power(pair.pcs_asset_id)
        standby = pcs.standby(pair.pcs_asset_id)
        response = {
            "ok": True,
            "stage": "pcs_standby_requested",
            "actions": [zero, standby],
        }
        self._update_runtime(pair_id, stage=response["stage"], last_action="prepare_pcs_standby", commanded_power_kw=0.0)
        self._audit(username, pair, "prepare_pcs_standby", 0, response)
        return response

    def configure_pcs(self, username: str, pair_id: str, confirmation: str) -> dict[str, Any]:
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        pcs = self._pcs(pair.pcs_asset_id)
        zero = pcs.set_zero_power(pair.pcs_asset_id)
        config_writes = pcs.configure_on_grid_pq(pair.pcs_asset_id)
        response = {
            "ok": True,
            "stage": "pcs_configured_on_grid_pq_zero_power",
            "actions": [zero, *config_writes],
            "control_mode": "on_grid_pq",
        }
        self._update_runtime(pair_id, stage=response["stage"], last_action="configure_pcs", commanded_power_kw=0.0)
        self._audit(username, pair, "configure_pcs", {"mode": "on_grid_pq", "power_kw": 0.0}, response)
        return response

    def _wait_until(
        self,
        predicate: Callable[[], tuple[bool, dict[str, Any]]],
        *,
        timeout_seconds: float,
        description: str,
        abort_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            if abort_event is not None and abort_event.is_set():
                raise RuntimeError("Sequence aborted by operator")
            ok, last = predicate()
            if ok:
                return last
            time.sleep(self.config.sample_interval_seconds)
        raise TimeoutError(f"Timed out waiting for {description}; last={last}")

    def start_pcs(
        self,
        username: str,
        pair_id: str,
        confirmation: str,
        verified_precharge_status: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del verified_precharge_status
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        ready = self.verify_ready(pair_id)
        if not ready["ok"]:
            raise ValueError(
                f"Battery/PCS input readiness failed: {[k for k, ok in ready['checks'].items() if not ok]}"
            )
        pcs = self._pcs(pair.pcs_asset_id)
        zero = pcs.set_zero_power(pair.pcs_asset_id)
        start = pcs.start(pair.pcs_asset_id)

        observed = self._wait_until(
            lambda: (
                (state := pcs.state(pair.pcs_asset_id)).online
                and state.running is True
                and state.faulted is not True,
                asdict(state),
            ),
            timeout_seconds=self.config.pcs_start_timeout_seconds,
            description="Elecod PCS running state",
        )
        response = {
            "ok": True,
            "stage": "pcs_started",
            "actions": [zero, start],
            "observed": observed,
        }
        self._update_runtime(pair_id, stage=response["stage"], last_action="start_pcs", commanded_power_kw=0.0)
        self._audit(username, pair, "start_pcs", 0xFF00, response)
        return response

    def _signed_gateway_power(self, direction: Direction, magnitude_kw: float) -> float:
        return -abs(float(magnitude_kw)) if direction == "charge" else abs(float(magnitude_kw))

    def _command_power_internal(
        self,
        username: str,
        pair: ControlPairConfig,
        direction: Direction,
        requested_power_kw: float,
    ) -> dict[str, Any]:
        precheck = self.precheck(pair.pair_id, direction, requested_power_kw)
        if not precheck["ok"]:
            failed = [key for key, ok in precheck["checks"].items() if not ok]
            raise ValueError(f"Power precheck failed: {failed}")
        signed = self._signed_gateway_power(direction, requested_power_kw)
        write = self._pcs(pair.pcs_asset_id).set_active_power_kw(pair.pcs_asset_id, signed)
        response = {
            "ok": True,
            "stage": "power_commanded",
            "direction": direction,
            "requested_power_kw": float(requested_power_kw),
            "commanded_signed_power_kw": signed,
            "effective_power_limit_kw": precheck["effective_power_limit_kw"],
            "write": write,
        }
        self._update_runtime(
            pair.pair_id,
            stage=response["stage"],
            last_action="set_power",
            last_error=None,
            requested_direction=direction,
            requested_power_kw=float(requested_power_kw),
            commanded_power_kw=signed,
        )
        self._audit(username, pair, "set_power", {"direction": direction, "power_kw": requested_power_kw}, response)
        return response

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
        response = self._command_power_internal(username, pair, direction, float(requested_power_kw))
        if self.config.runtime_monitor_enabled and float(requested_power_kw) > 0:
            self._ensure_runtime_monitor(username, pair)
        return response

    def zero_power(self, username: str, pair_id: str, confirmation: str) -> dict[str, Any]:
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        write = self._pcs(pair.pcs_asset_id).set_zero_power(pair.pcs_asset_id)
        response = {"ok": True, "stage": "zero_power_commanded", "write": write}
        self._update_runtime(pair_id, stage=response["stage"], last_action="zero_power", commanded_power_kw=0.0)
        self._audit(username, pair, "zero_power", 0.0, response)
        return response

    def verify_power(self, pair_id: str) -> dict[str, Any]:
        pair = self._pair(pair_id)
        pcs = self._pcs(pair.pcs_asset_id)
        setpoint = pcs.read_power_setpoint_kw(pair.pcs_asset_id)
        state = pcs.state(pair.pcs_asset_id)
        return {
            "ok": state.online,
            "pair": pair.model_dump(),
            "setpoint": {**setpoint, "value": setpoint.get("value_kw")},
            "actual_power": {"value": state.actual_active_power_kw, "unit": "kW"},
            "operating_state": {"running": state.running, "faulted": state.faulted},
            "timestamp": now_iso(),
        }

    # ------------------------------------------------------------------
    # Safe stop / abort
    # ------------------------------------------------------------------
    def _safe_stop_internal(
        self,
        username: str,
        pair: ControlPairConfig,
        *,
        open_bms: bool,
        reason: str,
    ) -> dict[str, Any]:
        with self._safe_stop_locks[pair.pair_id]:
            pcs = self._pcs(pair.pcs_asset_id)
            actions: list[dict[str, Any]] = []
            errors: list[str] = []
            try:
                actions.append({"zero_power": pcs.set_zero_power(pair.pcs_asset_id)})
            except Exception as error:
                errors.append(f"zero_power: {error}")
            # Verify power has fallen close to zero when readable, but always
            # continue to stop even if feedback is unavailable.
            try:
                self._wait_until(
                    lambda: (
                        abs(float((state := pcs.state(pair.pcs_asset_id)).actual_active_power_kw or 0.0))
                        <= max(1.0, self.config.power_tracking_tolerance_kw),
                        asdict(state),
                    ),
                    timeout_seconds=min(self.config.safe_stop_timeout_seconds, 10.0),
                    description="PCS active power near zero",
                )
            except Exception as error:
                errors.append(f"zero_power_verify: {error}")
            try:
                actions.append({"pcs_stop": pcs.stop(pair.pcs_asset_id)})
            except Exception as error:
                errors.append(f"pcs_stop: {error}")

            bms_disconnect: dict[str, Any] | None = None
            if open_bms:
                try:
                    if (
                        self.gateway_config.mode != "mock"
                        and self.config.allow_forced_bms_disconnect
                        and not self.gateway_config.bms.forced_disconnect_sequence_validated
                    ):
                        raise PermissionError(
                            "Lineage forced disconnect is enabled but its safe field sequence has not been validated"
                        )
                    result = self.battery.disconnect(pair.rack_id)
                    bms_disconnect = asdict(result)
                    if not result.ok:
                        errors.append(f"bms_disconnect: {result.message}")
                except Exception as error:
                    errors.append(f"bms_disconnect: {error}")

            ok = not errors or all(item.startswith("bms_disconnect: Forced Lineage") for item in errors)
            response = {
                "ok": ok,
                "stage": "safe_stopped" if ok else "safe_stop_completed_with_warnings",
                "reason": reason,
                "actions": actions,
                "bms_disconnect": bms_disconnect,
                "errors": errors,
                "note": (
                    "Lineage forced contactor opening remains capability-gated by default; PCS zero-power/stop is always attempted."
                ),
            }
            self._update_runtime(
                pair.pair_id,
                stage=response["stage"],
                last_action="safe_stop",
                last_error=None if ok else errors,
                commanded_power_kw=0.0,
                run_status="stopped" if ok else "stop_warning",
                monitor_active=False,
            )
            self._audit(username, pair, "safe_stop", {"open_bms": open_bms, "reason": reason}, response, "success" if ok else "warning")
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
        self._monitor_stop_events[pair_id].set()
        return self._safe_stop_internal(username, pair, open_bms=open_bms, reason="operator_safe_stop")

    def safe_stop_all(
        self,
        username: str,
        confirmation: str,
        *,
        open_bms: bool = False,
    ) -> dict[str, Any]:
        self._require_write_gates(confirmation)
        results: dict[str, Any] = {}
        for pair in self.config.pairs:
            if not pair.enabled:
                continue
            try:
                self._monitor_stop_events[pair.pair_id].set()
                results[pair.pair_id] = self._safe_stop_internal(
                    username, pair, open_bms=open_bms, reason="operator_safe_stop_all"
                )
            except Exception as error:
                results[pair.pair_id] = {"ok": False, "error": str(error)}
        return {
            "ok": all(item.get("ok") for item in results.values()) if results else True,
            "pairs": results,
            "timestamp": now_iso(),
        }

    def abort(
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
        self._monitor_stop_events[pair_id].set()
        stop = self._safe_stop_internal(username, pair, open_bms=open_bms, reason="operator_abort")
        self._update_runtime(
            pair_id,
            stage="aborted",
            last_action="abort",
            abort_requested=True,
            run_status="aborted",
            completed_at=now_iso(),
        )
        return {"ok": stop.get("ok", False), "stage": "aborted", "safe_stop": stop}

    # ------------------------------------------------------------------
    # Automatic sequence and ramping
    # ------------------------------------------------------------------
    @staticmethod
    def _automatic_step_template() -> list[dict[str, Any]]:
        return [
            {"key": "pcs_configuration", "status": "pending"},
            {"key": "rack_enable", "status": "pending"},
            {"key": "bms_precharge", "status": "pending"},
            {"key": "pcs_start", "status": "pending"},
            {"key": "power_precheck", "status": "pending"},
            {"key": "power_ramp", "status": "pending"},
            {"key": "power_tracking", "status": "pending"},
        ]

    def _set_run_step(self, pair_id: str, key: str, status: str, *, result: Any = None, message: str | None = None) -> None:
        with self._lock:
            steps = self._runtime[pair_id].setdefault("steps", [])
            step = next((item for item in steps if item.get("key") == key), None)
            if step is None:
                step = {"key": key}
                steps.append(step)
            step.update({"status": status, "updated_at": now_iso()})
            if result is not None:
                step["result"] = result
            if message is not None:
                step["message"] = message
            self._runtime[pair_id]["last_updated_at"] = now_iso()

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
            existing = self._sequence_futures.get(pair_id)
            if existing is not None and not existing.done():
                raise RuntimeError(f"Automatic sequence already active for {pair_id}")
            run_id = f"seq-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
            self._abort_events[pair_id].clear()
            self._monitor_stop_events[pair_id].clear()
            self._runtime[pair_id].update(
                {
                    "run_id": run_id,
                    "run_mode": "automatic",
                    "run_status": "queued",
                    "stage": "waiting_for_startup_lane",
                    "last_action": "automatic_start",
                    "last_error": None,
                    "started_at": now_iso(),
                    "completed_at": None,
                    "requested_direction": direction,
                    "requested_power_kw": target,
                    "commanded_power_kw": 0.0,
                    "abort_requested": False,
                    "steps": self._automatic_step_template(),
                }
            )
            future = self._sequence_executor.submit(
                self._automatic_worker,
                username,
                pair,
                direction,
                target,
                ramp_step_kw or self.config.automatic_power_ramp_step_kw,
                ramp_interval_seconds or self.config.automatic_power_ramp_interval_seconds,
                self._abort_events[pair_id],
            )
            self._sequence_futures[pair_id] = future
        response = {
            "ok": True,
            "accepted": True,
            "run_status": "queued",
            "stage": "waiting_for_startup_lane",
            "run_id": run_id,
            "pair_id": pair_id,
            "direction": direction,
            "target_power_kw": target,
            "status_endpoint": f"/api/control-sequence/{pair_id}/status?fresh=false",
            "all_pair_status_endpoint": "/api/control-sequence/status/all/compact",
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
        lock_acquired = False
        try:
            self._update_runtime(pair_id, run_status="queued", stage="waiting_for_startup_lane")
            while not lock_acquired:
                if abort_event.is_set():
                    raise RuntimeError("Sequence aborted by operator before startup")
                lock_acquired = self._startup_lock.acquire(timeout=0.25)
            self._update_runtime(pair_id, run_status="running", stage="automatic_sequence_running")

            self._set_run_step(pair_id, "pcs_configuration", "running")
            result = self.configure_pcs(username, pair_id, self.config.confirmation_phrase)
            self._set_run_step(pair_id, "pcs_configuration", "success", result=result)

            self._set_run_step(pair_id, "rack_enable", "running")
            result = self.enable_rack(username, pair_id, direction, target_power_kw, self.config.confirmation_phrase)
            self._set_run_step(pair_id, "rack_enable", "success" if result.get("ok") else "failed", result=result)
            if not result.get("ok"):
                raise ValueError("Lineage rack is not operational/healthy")

            self._set_run_step(pair_id, "bms_precharge", "running")
            initial = self.start_precharge(username, pair_id, self.config.confirmation_phrase)
            if not initial.get("ok"):
                observed = self._wait_until(
                    lambda: (
                        (ready := self.verify_ready(pair_id))["checks"].get("battery_ready", False),
                        ready,
                    ),
                    timeout_seconds=self.config.battery_prepare_timeout_seconds,
                    description="Lineage BMS automatic precharge/main-contactor readiness",
                    abort_event=abort_event,
                )
            else:
                observed = self.verify_ready(pair_id)
            self._set_run_step(
                pair_id,
                "bms_precharge",
                "success",
                result={"initial": initial, "observed": observed},
            )

            self._set_run_step(pair_id, "pcs_start", "running")
            result = self.start_pcs(username, pair_id, self.config.confirmation_phrase)
            self._set_run_step(pair_id, "pcs_start", "success", result=result)

            self._set_run_step(pair_id, "power_precheck", "running")
            precheck = self.precheck(pair_id, direction, target_power_kw)
            if not precheck["ok"]:
                raise ValueError(
                    f"Power precheck failed: {[key for key, ok in precheck['checks'].items() if not ok]}"
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
            tracked = self._wait_for_power_tracking(pair, direction, target_power_kw, abort_event)
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
            if abort_event.is_set():
                self._update_runtime(
                    pair_id,
                    stage="automatic_sequence_aborted",
                    last_action="abort",
                    last_error="Aborted by operator",
                    run_status="aborted",
                    completed_at=now_iso(),
                    commanded_power_kw=0.0,
                )
            else:
                LOGGER.exception("Vendor-neutral automatic sequence failed pair=%s", pair_id)
                stop = self._safe_stop_internal(
                    username,
                    pair,
                    open_bms=False,
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
                    failure_safe_stop=stop,
                )
        finally:
            if lock_acquired:
                self._startup_lock.release()

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
            self._pcs(pair.pcs_asset_id).set_zero_power(pair.pcs_asset_id)
            return []
        writes: list[dict[str, Any]] = []
        current = 0.0
        while current + 1e-9 < target:
            if abort_event is not None and abort_event.is_set():
                raise RuntimeError("Sequence aborted by operator")
            next_power = min(target, current + float(step_kw))
            writes.append(self._command_power_internal(username, pair, direction, next_power))
            current = next_power
            if current < target:
                time.sleep(interval_seconds)
        return writes

    def _wait_for_power_tracking(
        self,
        pair: ControlPairConfig,
        direction: Direction,
        target_power_kw: float,
        abort_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        signed_target = self._signed_gateway_power(direction, target_power_kw)
        tolerance = max(self.config.power_tracking_tolerance_kw, abs(signed_target) * 0.1)

        def predicate() -> tuple[bool, dict[str, Any]]:
            result = self.verify_power(pair.pair_id)
            setpoint = result["setpoint"].get("value")
            actual = result["actual_power"].get("value")
            ok = (
                setpoint is not None
                and actual is not None
                and abs(float(setpoint) - signed_target) <= 0.5
                and abs(float(actual) - signed_target) <= tolerance
            )
            return ok, result

        return self._wait_until(
            predicate,
            timeout_seconds=self.config.power_tracking_timeout_seconds,
            description=f"PCS power tracking {signed_target} kW",
            abort_event=abort_event,
        )

    def next_step(
        self,
        username: str,
        pair_id: str,
        direction: Direction,
        requested_power_kw: float,
        confirmation: str,
    ) -> dict[str, Any]:
        runtime = self._runtime_snapshot(pair_id)
        stage = runtime.get("stage")
        if stage in {"idle", "precheck_failed", "precheck_passed"}:
            return self.configure_pcs(username, pair_id, confirmation)
        if stage.startswith("pcs_configured") or stage.startswith("rack_enable"):
            return self.enable_rack(username, pair_id, direction, requested_power_kw, confirmation)
        if stage in {"rack_enable_not_applicable_bms_automatic", "waiting_for_bms_automatic_precharge"}:
            return self.start_precharge(username, pair_id, confirmation)
        if stage in {"ready", "precharge_already_complete"}:
            return self.start_pcs(username, pair_id, confirmation)
        if stage == "pcs_started":
            return self.precheck(pair_id, direction, requested_power_kw)
        if stage == "precheck_passed":
            return self.set_power(username, pair_id, direction, requested_power_kw, confirmation)
        return {
            "ok": False,
            "stage": stage,
            "message": "No automatic next-step mapping for the current state; inspect pair status.",
        }

    # ------------------------------------------------------------------
    # Runtime safety monitor
    # ------------------------------------------------------------------
    def _runtime_monitor_status(self, pair: ControlPairConfig) -> dict[str, Any]:
        try:
            return self.status(pair.pair_id, fresh=True)
        except Exception as error:
            return {
                "summary": {},
                "workflow": {"hard_blocked": True},
                "errors": [{"target": "runtime_monitor", "error": str(error)}],
            }

    def _ensure_runtime_monitor(self, username: str, pair: ControlPairConfig) -> None:
        with self._lock:
            thread = self._monitor_threads.get(pair.pair_id)
            if thread is not None and thread.is_alive():
                return
            self._monitor_stop_events[pair.pair_id].clear()
            thread = threading.Thread(
                target=self._runtime_monitor_worker,
                args=(username, pair),
                name=f"pair-monitor-{pair.pair_id}",
                daemon=True,
            )
            self._monitor_threads[pair.pair_id] = thread
            self._runtime[pair.pair_id]["monitor_active"] = True
            thread.start()

    def _runtime_monitor_worker(self, username: str, pair: ControlPairConfig) -> None:
        stop_event = self._monitor_stop_events[pair.pair_id]
        stats = self._runtime_monitor_stats[pair.pair_id]
        try:
            while not stop_event.is_set():
                runtime = self._runtime_snapshot(pair.pair_id)
                commanded = float(runtime.get("commanded_power_kw") or 0.0)
                if abs(commanded) <= 1e-9:
                    return
                status = self._runtime_monitor_status(pair)
                stats["samples"] += 1
                stats["last_sample_at"] = now_iso()
                violations: list[str] = []
                s = status.get("summary", {})
                if status.get("errors"):
                    violations.append("runtime_read_error")
                if status.get("workflow", {}).get("hard_blocked"):
                    violations.append("hard_blocked")
                if not s.get("contactors_ready"):
                    violations.append("battery_contactors_not_ready")
                if s.get("pcs_faulted"):
                    violations.append("pcs_fault")
                if not s.get("pcs_running"):
                    violations.append("pcs_not_running")
                direction: Direction = "charge" if commanded < 0 else "discharge"
                allowed = s.get("charge_allowed") if direction == "charge" else s.get("discharge_allowed")
                if not allowed:
                    violations.append(f"bms_{direction}_not_allowed")
                dynamic_limit = (
                    s.get("bms_charge_power_limit_kw")
                    if direction == "charge"
                    else s.get("bms_discharge_power_limit_kw")
                )
                if dynamic_limit is not None and abs(commanded) > float(dynamic_limit) + 1e-9:
                    violations.append("command_exceeds_dynamic_bms_limit")
                actual = s.get("pcs_actual_power_kw")
                if actual is not None:
                    tolerance = max(self.config.power_tracking_tolerance_kw, abs(commanded) * 0.15)
                    if abs(float(actual) - commanded) > tolerance:
                        violations.append("power_tracking_error")

                stats["last_errors"] = status.get("errors", [])
                stats["last_violations"] = violations
                if violations:
                    stats["unverified_samples"] += 1
                    stats["safety_stops"] += 1
                    self._safe_stop_internal(
                        username,
                        pair,
                        open_bms=False,
                        reason=f"runtime_monitor_violation:{','.join(violations)}",
                    )
                    self._update_runtime(
                        pair.pair_id,
                        run_status="failed",
                        stage="runtime_safety_stop",
                        last_error=violations,
                        monitor_active=False,
                    )
                    return
                stats["verified_samples"] += 1
                stop_event.wait(self.config.runtime_monitor_interval_seconds)
        finally:
            self._update_runtime(pair.pair_id, monitor_active=False)

    # ------------------------------------------------------------------
    # Capabilities / software-completeness reporting
    # ------------------------------------------------------------------
    def capabilities(self) -> dict[str, Any]:
        return {
            "controller": "vendor_neutral_pair_controller",
            "architecture": "frozen_kinetics_derived_ornate_gateway",
            "bms_vendor": self.gateway_config.bms.vendor,
            "pcs_vendor": self.gateway_config.pcs.vendor,
            "pairs": [pair.model_dump() for pair in self.config.pairs],
            "battery_capabilities": asdict(self.battery.capabilities),
            "pcs_capabilities": {
                asset_id: asdict(adapter.capabilities) for asset_id, adapter in self._pcs_adapters.items()
            },
            "software_features": {
                "pairing": True,
                "staged_control": True,
                "automatic_sequence": True,
                "charge_discharge": True,
                "dynamic_bms_power_limits": True,
                "system_bms_aggregate_limit": True,
                "power_ramp": True,
                "power_tracking": True,
                "runtime_monitor": True,
                "safe_stop": True,
                "safe_stop_all": True,
                "command_audit": True,
                "alarm_history": True,
                "historian": True,
                "rest_api_compatibility": True,
            },
            "commissioning_gates": {
                "lineage_float_word_order": self.gateway_config.bms.word_order,
                "lineage_register_offset": self.gateway_config.bms.address_offset,
                "lineage_warning_operation_allowed": self.config.allow_bms_warning_operation,
                "lineage_forced_disconnect_allowed": self.config.allow_forced_bms_disconnect,
                "elecod_power_sign_validated": self.gateway_config.pcs.power_sign_validated,
                "elecod_positive_power_is_discharge": self.gateway_config.pcs.positive_power_is_discharge,
                "control_enabled": self.config.enabled,
                "automatic_sequence_enabled": self.config.allow_full_automatic_sequence,
            },
            "known_protocol_gaps": [
                "Lineage V05 does not define a normal EMS precharge command/success register.",
                "Lineage V05 FLOAT32 word order requires hardware confirmation.",
                "Lineage rack/system current sign requires hardware confirmation.",
                "Elecod active-power sign requires low-power hardware confirmation before non-zero commands.",
                "Lineage forced contactor open sequencing remains disabled by default until vendor approval.",
            ],
            "timestamp": now_iso(),
        }
