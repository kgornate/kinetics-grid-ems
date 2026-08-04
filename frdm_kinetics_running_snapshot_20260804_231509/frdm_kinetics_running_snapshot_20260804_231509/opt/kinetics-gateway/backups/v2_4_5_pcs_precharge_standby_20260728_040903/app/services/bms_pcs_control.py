from __future__ import annotations

import logging
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal

from app.assets.bms_driver import BmsModbusDriver
from app.assets.pcs_driver import PcsModbusDriver
from app.core.config import ControlPairConfig, ControlSequenceConfig, GatewayConfig
from app.storage.sqlite_store import SQLiteStore

LOGGER = logging.getLogger(__name__)
Direction = Literal["charge", "discharge"]


PCS_STOPPED_STATE = 0x0001
PCS_FAULT_SHUTDOWN_BIT = 0x0400
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
    """Manual, staged BMS-to-PCS commissioning controller.

    The service deliberately exposes each hardware write as a separate stage.
    No automatic control loop runs in the background. A full automatic
    sequence remains blocked until all stages are validated on the real BESS.
    """

    def __init__(
        self,
        gateway_config: GatewayConfig,
        bms_driver: BmsModbusDriver,
        pcs_driver: PcsModbusDriver,
        store: SQLiteStore,
    ) -> None:
        self.gateway_config = gateway_config
        self.config: ControlSequenceConfig = gateway_config.control_sequence
        self.bms_driver = bms_driver
        self.pcs_driver = pcs_driver
        self.store = store
        self._lock = threading.RLock()
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

    def status(self, pair_id: str, *, fresh: bool = True) -> dict[str, Any]:
        pair = self._pair(pair_id)
        if not fresh:
            with self._lock:
                return deepcopy(self._runtime[pair_id])

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
            ("pcs_operating_state", self.pcs_driver.read_point, pair.pcs_asset_id, "operating_state"),
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

        rack_voltage = self._value(reads["rack_voltage"])
        charge_limit = self._value(reads["rack_charge_limit"])
        discharge_limit = self._value(reads["rack_discharge_limit"])
        pcs_dc_bus = self._value(reads["pcs_dc_bus_voltage"])
        pcs_state = self._value(reads["pcs_operating_state"])
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

        # This BMS firmware can keep the 0x1001 summary system-fault bit active
        # after the HMI's Level-1 fault is cleared. For commissioning, use the
        # documented detailed fault words as the energising-command gate while
        # still exposing the raw summary bit for diagnostics.
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

        blockers = {
            "emergency_stop_fault": bank_fault_bits.get("emergency_stop_fault") == 1,
            # Legacy key used by the staged state machine. It now represents
            # confirmed documented critical faults, not the stale 0x1001 bit.
            "system_fault": documented_critical_fault,
            "documented_critical_fault": documented_critical_fault,
            "summary_system_fault_bit": summary_system_fault_bit,
            "detailed_fault_raw": detailed_fault_raw,
            "system_charge_prohibited": bank_fault_bits.get("system_full") == 1,
            "system_discharge_prohibited": bank_fault_bits.get("system_empty") == 1,
            "pcs_control_fault": bank_fault_bits.get("pcs_ctrl") == 1,
        }

        result = {
            "pair": pair.model_dump(),
            "timestamp": now_iso(),
            "runtime": deepcopy(self._runtime[pair_id]),
            "write_gates": {
                "control_sequence_enabled": self.config.enabled,
                "gateway_mode": self.gateway_config.mode,
                "bms_write_enabled": self.gateway_config.bms.write_enabled,
                "pcs_write_enabled": self.gateway_config.pcs.write_enabled,
                "full_automatic_sequence_allowed": self.config.allow_full_automatic_sequence,
            },
            "summary": {
                "rack_enabled": enable_bit,
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
        return result

    def precheck(self, pair_id: str, direction: Direction, requested_power_kw: float) -> dict[str, Any]:
        pair = self._pair(pair_id)
        requested = float(requested_power_kw)
        status = self.status(pair_id, fresh=True)
        summary = status["summary"]
        checks: dict[str, bool] = {
            "all_required_reads_ok": not status["errors"],
            "rack_voltage_valid": bool(summary["rack_voltage_valid"]),
            "pcs_not_fault_shutdown": not bool(summary["pcs_fault_shutdown"]),
            "no_emergency_stop": not bool(summary["blockers"]["emergency_stop_fault"]),
            "no_system_fault": not bool(summary["blockers"]["system_fault"]),
            "requested_power_non_negative": requested >= 0,
            "requested_power_within_240kw_limit": requested <= self.config.max_abs_power_kw,
        }
        if direction == "charge":
            current_limit = summary["rack_charge_current_limit_a"]
            dynamic_limit = summary["bms_charge_power_limit_kw"]
            checks["bms_direction_not_prohibited"] = not bool(summary["blockers"]["system_charge_prohibited"])
        elif direction == "discharge":
            current_limit = summary["rack_discharge_current_limit_a"]
            dynamic_limit = summary["bms_discharge_power_limit_kw"]
            checks["bms_direction_not_prohibited"] = not bool(summary["blockers"]["system_discharge_prohibited"])
        else:
            raise ValueError("Direction must be charge or discharge")
        checks["bms_current_limit_available"] = current_limit is not None and float(current_limit) >= self.config.minimum_bms_current_limit_a
        if self.config.enforce_dynamic_bms_power_limit:
            checks["requested_power_within_dynamic_bms_limit"] = dynamic_limit is not None and requested <= float(dynamic_limit) + 1e-9
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
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        status = self.status(pair_id, fresh=True)
        requested = float(requested_power_kw)
        basic_checks = {
            "all_required_reads_ok": not status["errors"],
            "rack_voltage_valid": bool(status["summary"]["rack_voltage_valid"]),
            "pcs_not_fault_shutdown": not bool(status["summary"]["pcs_fault_shutdown"]),
            "no_emergency_stop": not bool(status["summary"]["blockers"]["emergency_stop_fault"]),
            "no_system_fault": not bool(status["summary"]["blockers"]["system_fault"]),
            "requested_power_non_negative": requested >= 0,
            "requested_power_within_240kw_limit": requested <= self.config.max_abs_power_kw,
        }
        if not all(basic_checks.values()):
            raise ValueError(f"Rack-enable precheck failed: {[k for k, v in basic_checks.items() if not v]}")
        try:
            write = self.bms_driver.write_indexed_point(
                "bms_bank", "rack1_enable_control", pair.rack_id - 1, 1
            )
            response = {
                "ok": True,
                "stage": "rack_enabled",
                "write": write,
                "precheck": {"checks": basic_checks, "status": status},
            }
            self._update_runtime(pair_id, stage="rack_enabled", last_action="enable_rack", last_error=None)
            self._audit(username, pair, "enable_rack", {"direction": direction, "power_kw": requested_power_kw}, response)
            return response
        except Exception as error:
            self._update_runtime(pair_id, stage="error", last_action="enable_rack", last_error=str(error))
            self._audit(username, pair, "enable_rack", requested_power_kw, {"ok": False, "error": str(error)}, "failed")
            raise

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
            "rack_enabled": summary.get("rack_enabled") == 1,
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
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        status = self.status(pair_id, fresh=True)
        if status["summary"]["rack_enabled"] != 1:
            raise ValueError("Rack enable feedback is not active")
        rack_asset = f"bms_rack_{pair.rack_id}"
        try:
            write = self.bms_driver.write_point(rack_asset, "start_pre_chg_operate", 1)
            response = {"ok": True, "stage": "precharge_requested", "write": write}
            self._update_runtime(pair_id, stage="precharge_requested", last_action="start_precharge", last_error=None)
            self._audit(username, pair, "start_precharge", 1, response)
            return response
        except Exception as error:
            self._update_runtime(pair_id, stage="error", last_action="start_precharge", last_error=str(error))
            self._audit(username, pair, "start_precharge", 1, {"ok": False, "error": str(error)}, "failed")
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
            "rack_disabled": summary.get("rack_enabled") == 0,
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
                and summary["rack_enabled"] == 1
                and bool(summary["rack_voltage_valid"])
                and bool(summary["pcs_dc_bus_valid"])
                and bool(summary["contactors_ready"])
                and (bool(summary["precharge_success"]) or not self.config.require_precharge_success)
                and not bool(summary["pcs_fault_shutdown"])
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

    def configure_pcs(self, username: str, pair_id: str, confirmation: str) -> dict[str, Any]:
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        ready = self.verify_ready(pair_id)
        if not ready["ok"]:
            raise ValueError("BMS contactor/DC-bus readiness verification failed")
        pcs_state = int(ready["samples"][-1]["summary"]["pcs_operating_state"] or 0)
        if pcs_state not in {PCS_STOPPED_STATE, 8}:
            raise ValueError(f"PCS must be stopped or standby before base mode configuration; state={pcs_state}")
        commands = [
            ("remote_local_mode", PCS_REMOTE_VALUE),
            ("product_run_mode", PCS_PQ_PRODUCT_MODE),
            ("pq_work_mode", PCS_CONSTANT_POWER_MODE),
            ("active_power_setpoint", 0.0),
        ]
        writes = []
        try:
            for key, value in commands:
                writes.append(self.pcs_driver.write_point(pair.pcs_asset_id, key, value))
            response = {"ok": True, "stage": "pcs_configured", "writes": writes}
            self._update_runtime(pair_id, stage="pcs_configured", last_action="configure_pcs", last_error=None)
            self._audit(username, pair, "configure_pcs", dict(commands), response)
            return response
        except Exception as error:
            self._update_runtime(pair_id, stage="error", last_action="configure_pcs", last_error=str(error))
            self._audit(username, pair, "configure_pcs", dict(commands), {"ok": False, "error": str(error)}, "failed")
            raise

    def start_pcs(self, username: str, pair_id: str, confirmation: str) -> dict[str, Any]:
        pair = self._pair(pair_id)
        self._require_write_gates(confirmation)
        ready = self.verify_ready(pair_id)
        if not ready["ok"]:
            raise ValueError("BMS contactor/DC-bus readiness verification failed")
        try:
            write = self.pcs_driver.write_point(pair.pcs_asset_id, "remote_on_off_command", PCS_START_VALUE)
            deadline = time.monotonic() + self.config.pcs_start_timeout_seconds
            state = None
            while time.monotonic() < deadline:
                state = self.pcs_driver.read_point(pair.pcs_asset_id, "operating_state")
                raw = int(state.get("value") or 0)
                if raw & PCS_FAULT_SHUTDOWN_BIT:
                    raise RuntimeError(f"PCS entered fault shutdown state: {raw}")
                if raw != PCS_STOPPED_STATE:
                    break
                time.sleep(self.config.sample_interval_seconds)
            if state is None or int(state.get("value") or 0) == PCS_STOPPED_STATE:
                raise TimeoutError("PCS remained stopped after start command")
            response = {"ok": True, "stage": "pcs_started", "write": write, "operating_state": state}
            self._update_runtime(pair_id, stage="pcs_started", last_action="start_pcs", last_error=None)
            self._audit(username, pair, "start_pcs", PCS_START_VALUE, response)
            return response
        except Exception as error:
            self._update_runtime(pair_id, stage="error", last_action="start_pcs", last_error=str(error))
            self._audit(username, pair, "start_pcs", PCS_START_VALUE, {"ok": False, "error": str(error)}, "failed")
            raise

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
        precheck = self.precheck(pair_id, direction, requested_power_kw)
        if not precheck["ok"]:
            raise ValueError(f"Power precheck failed: {[k for k, v in precheck['checks'].items() if not v]}")
        ready = self.verify_ready(pair_id)
        if not ready["ok"]:
            raise ValueError("BMS contactor/DC-bus readiness verification failed")
        state = int(self.pcs_driver.read_point(pair.pcs_asset_id, "operating_state").get("value") or 0)
        if state == PCS_STOPPED_STATE or state & PCS_FAULT_SHUTDOWN_BIT:
            raise ValueError(f"PCS is not running/ready for power command; state={state}")
        requested = float(requested_power_kw)
        signed_command = -requested if direction == "charge" else requested
        try:
            write = self.pcs_driver.write_point(pair.pcs_asset_id, "active_power_setpoint", signed_command)
            response = {
                "ok": True,
                "stage": "power_commanded",
                "direction": direction,
                "requested_power_kw": requested,
                "commanded_signed_power_kw": signed_command,
                "effective_power_limit_kw": precheck["effective_power_limit_kw"],
                "write": write,
            }
            self._update_runtime(
                pair_id,
                stage="power_commanded",
                last_action="set_power",
                last_error=None,
                requested_direction=direction,
                requested_power_kw=requested,
                commanded_power_kw=signed_command,
            )
            self._audit(username, pair, "set_power", {"direction": direction, "power_kw": requested}, response)
            return response
        except Exception as error:
            self._update_runtime(pair_id, stage="error", last_action="set_power", last_error=str(error))
            self._audit(username, pair, "set_power", {"direction": direction, "power_kw": requested}, {"ok": False, "error": str(error)}, "failed")
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
        actions: list[dict[str, Any]] = []
        errors: list[str] = []
        for key, value in (("active_power_setpoint", 0.0), ("remote_on_off_command", PCS_STOP_VALUE)):
            try:
                actions.append(self.pcs_driver.write_point(pair.pcs_asset_id, key, value))
            except Exception as error:
                errors.append(f"{key}: {error}")
        if open_bms:
            rack_asset = f"bms_rack_{pair.rack_id}"
            try:
                actions.append(self.bms_driver.write_point(rack_asset, "start_pre_chg_operate", 0))
            except Exception as error:
                errors.append(f"bms_precharge_stop: {error}")
            try:
                actions.append(
                    self.bms_driver.write_indexed_point(
                        "bms_bank", "rack1_enable_control", pair.rack_id - 1, 2
                    )
                )
            except Exception as error:
                errors.append(f"bms_rack_disable: {error}")
        response = {
            "ok": not errors,
            "stage": "stopped" if not open_bms else "stopped_and_bms_open_requested",
            "actions": actions,
            "errors": errors,
        }
        self._update_runtime(
            pair_id,
            stage=response["stage"],
            last_action="safe_stop",
            last_error=errors or None,
            commanded_power_kw=0.0,
        )
        self._audit(username, pair, "safe_stop", {"open_bms": open_bms}, response, "success" if not errors else "failed")
        if errors:
            raise RuntimeError("; ".join(errors))
        return response

    def capabilities(self) -> dict[str, Any]:
        return {
            "controller": "manual_staged_bms_pcs_control",
            "enabled": self.config.enabled,
            "full_automatic_sequence_allowed": self.config.allow_full_automatic_sequence,
            "pairs": [pair.model_dump() for pair in self.config.pairs],
            "safety_limits": {
                "bms_rack_voltage_v": [self.config.bms_rack_voltage_min_v, self.config.bms_rack_voltage_max_v],
                "pcs_dc_bus_voltage_v": [self.config.pcs_dc_bus_voltage_min_v, self.config.pcs_dc_bus_voltage_max_v],
                "max_abs_power_kw": self.config.max_abs_power_kw,
                "positive_power_means": "discharge",
                "negative_power_means": "charge",
            },
            "bms_registers": {
                "rack_enable_control": "BAU 0x3005 + rack_index, 1=enable, 2=disable",
                "insulation_sampling": "BCU 0x0401, 1=start; do not retrigger for at least 3 seconds; vendor pass threshold not yet configured",
                "precharge_control": "BCU 0x0402, 1=start, 0=stop/open main positive",
                "fault_recovery": "BAU 0x3047, pulse 1 then 0; only while PCS stopped, rack disabled and contactors open",
                "rack_voltage": "BCU 0x0231, S16, 0.1 V",
                "precharge_state": "BCU 0x0018, 3=success",
                "contactor_state": "BCU 0x001F, bit0 positive, bit2 negative",
                "charge_current_limit": "BCU 0x0225, U16, 0.1 A",
                "discharge_current_limit": "BCU 0x0226, U16, 0.1 A",
            },
            "pcs_registers": {
                "dc_bus_voltage": "0x1100, S16, 0.1 V",
                "operating_state": "0x1200",
                "remote_on_off": "0x1400, 0xFF00=start, 0x00FF=stop",
                "remote_local_mode": "0x1402, 0x00FF=remote",
                "product_run_mode": "0x1406, 1=PQ",
                "pq_work_mode": "0x1407, 0=constant power",
                "active_power_setpoint": "0x1409, S16, 0.1 kW, +discharge/-charge",
                "actual_active_power": "0x110D, S16, 0.1 kW",
            },
            "confirmation_phrase": self.config.confirmation_phrase,
        }
