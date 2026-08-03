from __future__ import annotations

import threading
import time
from typing import Any

from app.core.config import GatewayConfig, PcsDeviceConfig
from app.services import bms_pcs_control as control_module
from app.services.bms_pcs_control import BmsPcsControlService


class FakeStore:
    def __init__(self) -> None:
        self.commands: list[tuple[Any, ...]] = []
        self.events: list[tuple[Any, ...]] = []

    def audit_command(self, *args: Any, **kwargs: Any) -> None:
        self.commands.append(args)

    def event(self, *args: Any, **kwargs: Any) -> None:
        self.events.append(args)


class FakeBms:
    def __init__(self) -> None:
        self.rack_enabled = 0
        self.precharge = 0
        self.system_fault = False
        self.recovery_value = 0
        self.bau_connect = 0
        self.local_remote_mode = 2

    def read_point(self, asset_id: str, key: str) -> dict[str, Any]:
        values = {
            "external_fault_state": {"value": 0x1C00 if self.system_fault else 0, "raw": 0x1C00 if self.system_fault else 0, "bitfields": {
                "emergency_stop_fault": 0,
                "system_fault": 1 if self.system_fault else 0,
                "system_full": 1 if self.system_fault else 0,
                "system_empty": 1 if self.system_fault else 0,
                "pcs_ctrl": 0,
            }},
            "rack_enable_state_l16": {"value": self.rack_enabled},
            "auto_onnected": {"value": self.bau_connect},
            "local_remote_ctrl": {"value": self.local_remote_mode},
            "vrack": {"value": 1389.0},
            "irack_chg_limit": {"value": 200.0},
            "irack_dsg_limit": {"value": 200.0},
            "pre_charge_state": {"value": 3 if self.precharge else 0},
            "start_pre_chg_operate": {"value": self.precharge},
            "start_insulation_sampleing": {"value": 0},
            "ir": {"value": 20000},
            "ir_pos": {"value": 20000},
            "ir_neg": {"value": 20000},
            "external_level1_alarm": {"value": 0, "raw": 0, "bitfields": {}},
            "bcu_external_lv1_alm_sum_ii": {"value": 0, "raw": 0, "bitfields": {}},
            "rack_fault": {"value": 0, "raw": 0, "bitfields": {}},
            "fault_info_sum2": {"value": 0, "raw": 0, "bitfields": {}},
            "bcu_external_fault_alarm": {"value": 0x4000 if self.system_fault else 0, "raw": 0x4000 if self.system_fault else 0, "bitfields": {"reserved1": 1 if self.system_fault else 0}},
            "external_critical": {"value": 0, "raw": 0, "bitfields": {}},
            "external_stop_alarm2": {"value": 0, "raw": 0, "bitfields": {}},
            "bcu_run_state": {"value": 4},
            "contactor_state": {"value": 5 if self.precharge else 0, "bitfields": {
                "positive_contactor_state": 1 if self.precharge else 0,
                "negitive_contactor_state": 1 if self.precharge else 0,
                "pre_charge_contactor_state": 0,
            }},
        }
        return values[key]

    def write_indexed_point(self, asset_id: str, key: str, index: int, value: int) -> dict[str, Any]:
        self.rack_enabled = 1 if value == 1 else 0
        return {"ok": True, "point_key": key, "index": index, "written_value": value}

    def write_point(self, asset_id: str, key: str, value: int) -> dict[str, Any]:
        if key == "auto_onnected":
            self.bau_connect = value
            self.precharge = 1 if value == 1 else 0
        elif key == "start_pre_chg_operate":
            self.precharge = value
        elif key == "one_click_revert":
            self.recovery_value = value
            if value == 1:
                self.system_fault = False
        return {"ok": True, "point_key": key, "written_value": value, "readback": {"value": value}}


class FakePcs:
    def __init__(self) -> None:
        self.state = 1
        self.values = {
            "remote_on_off_command": 255,
            "remote_local_mode": 65280,
            "product_run_mode": 1,
            "pq_work_mode": 0,
            "active_power_setpoint": 0.0,
        }

    def read_point(self, asset_id: str, key: str) -> dict[str, Any]:
        values = {
            "dc_bus_voltage": 1389.0,
            "battery_voltage": 1389.0,
            "operating_state": self.state,
            "status_word_1": {"value": 1, "raw": 1, "bitfields": {"remote_feedback": 1}},
            "status_word_2": {"value": 0, "raw": 0, "bitfields": {"dc_breaker_state": 0}},
            "reg_1210": {"value": 128 if self.state != 1 else 0, "raw": 128 if self.state != 1 else 0, "bitfields": {"dc_breaker_feedback": 1 if self.state != 1 else 0}},
            "reg_121a": {"value": 0, "raw": 0, "bitfields": {"dc_soft_start_fault": 0, "dc_soft_start_relay_fault": 0}},
            "grid_active_power": self.values["active_power_setpoint"],
            **self.values,
        }
        value = values[key]
        if isinstance(value, dict):
            return {**value, "point_key": key}
        return {"value": value, "point_key": key}

    def write_point(self, asset_id: str, key: str, value: Any) -> dict[str, Any]:
        self.values[key] = value
        if key == "remote_on_off_command":
            self.state = 8 if value == 65280 else 1
        return {"ok": True, "point_key": key, "written_value": value, "readback": {"value": value}}


def configured_service() -> BmsPcsControlService:
    config = GatewayConfig()
    config.mode = "control_enabled"
    config.bms.write_enabled = True
    config.pcs.enabled = True
    config.pcs.write_enabled = True
    config.pcs.transport = "rtu"
    config.pcs.devices = [
        PcsDeviceConfig(asset_id="pcs_1", unit_id=1, enabled=True),
        PcsDeviceConfig(asset_id="pcs_2", unit_id=2, enabled=False),
        PcsDeviceConfig(asset_id="pcs_3", unit_id=3, enabled=False),
        PcsDeviceConfig(asset_id="pcs_4", unit_id=4, enabled=False),
    ]
    config.control_sequence.enabled = True
    config.control_sequence.valid_samples_required = 1
    config.control_sequence.sample_interval_seconds = 0.001
    config.control_sequence.pcs_start_timeout_seconds = 0.1
    return BmsPcsControlService(config, FakeBms(), FakePcs(), FakeStore())


def test_staged_sequence_happy_path() -> None:
    service = configured_service()
    confirm = "EXECUTE_STAGE_WRITE"
    assert service.precheck("pair_1", "discharge", 10.0)["ok"] is False
    assert service.enable_rack("internal", "pair_1", "discharge", 10.0, confirm)["ok"] is True
    assert service.start_precharge("internal", "pair_1", confirm)["ok"] is True
    assert service.configure_pcs("internal", "pair_1", confirm)["ok"] is True
    assert service.start_pcs("internal", "pair_1", confirm)["ok"] is True
    assert service.verify_ready("pair_1")["ok"] is True
    assert service.precheck("pair_1", "discharge", 10.0)["ok"] is True
    result = service.set_power("internal", "pair_1", "discharge", 10.0, confirm)
    assert result["commanded_signed_power_kw"] == 10.0
    assert service.verify_power("pair_1")["setpoint"]["value"] == 10.0
    assert service.safe_stop("internal", "pair_1", confirm, open_bms=True)["ok"] is True


def test_power_above_project_cap_is_rejected() -> None:
    service = configured_service()
    result = service.precheck("pair_1", "charge", 241.0)
    assert result["ok"] is False
    assert result["checks"]["requested_power_within_240kw_limit"] is False


def test_bms_recovery_pulse_clears_latched_fault_from_safe_state() -> None:
    service = configured_service()
    service.bms_driver.system_fault = True
    result = service.recover_bms("internal", "pair_1", "EXECUTE_STAGE_WRITE")
    assert result["ok"] is True
    assert result["fault_cleared"] is True
    assert result["stage"] == "bms_recovered"
    assert [action["written_value"] for action in result["actions"]] == [1]
    assert service.bms_driver.recovery_value == 1


def test_bms_recovery_is_blocked_if_contactors_are_closed() -> None:
    service = configured_service()
    service.bms_driver.system_fault = True
    service.bms_driver.precharge = 1
    try:
        service.recover_bms("internal", "pair_1", "EXECUTE_STAGE_WRITE")
    except ValueError as error:
        assert "positive_contactor_open" in str(error)
    else:
        raise AssertionError("Recovery should be blocked while contactors are closed")


def _healthy_runtime_status() -> dict[str, Any]:
    return {
        "summary": {
            "contactors_ready": True,
            "pcs_dc_breaker_feedback_closed": True,
            "rack_charge_current_limit_a": 200.0,
            "rack_discharge_current_limit_a": 200.0,
            "bms_charge_power_limit_kw": 240.0,
            "bms_discharge_power_limit_kw": 240.0,
            "blockers": {
                "system_charge_prohibited": False,
                "system_discharge_prohibited": False,
            },
        },
        "workflow": {"hard_blocked": False},
        "errors": [],
        "refresh": {"source": "background_poll_cache", "freshness": {}},
        "runtime_verification": {
            "verified": True,
            "deferred": False,
            "source": "background_poll_cache",
        },
    }


def _deferred_runtime_status() -> dict[str, Any]:
    return {
        "summary": {},
        "workflow": {"hard_blocked": False},
        "errors": [{"target": "pcs", "error": "stale"}],
        "refresh": {
            "source": "runtime_verification_deferred",
            "freshness": {},
            "busy": True,
            "busy_reason": "global_refresh_lane_busy",
        },
        "runtime_verification": {
            "verified": False,
            "deferred": True,
            "reason": "refresh_lane_busy",
        },
    }


def test_runtime_monitor_recovers_from_temporary_refresh_contention() -> None:
    service = configured_service()
    service.config.runtime_monitor_interval_seconds = 0.001
    service.config.runtime_monitor_refresh_wait_seconds = 0.001
    service.config.runtime_monitor_max_unverified_seconds = 0.1
    service._update_runtime(
        "pair_1",
        commanded_power_kw=10.0,
        requested_power_kw=10.0,
        requested_direction="discharge",
        run_status="success",
    )

    samples = 0
    safe_stops: list[str] = []

    def sample(pair_id: str, pair: Any) -> dict[str, Any]:
        nonlocal samples
        samples += 1
        if samples <= 3:
            return _deferred_runtime_status()
        service._update_runtime(pair_id, commanded_power_kw=0.0)
        return _healthy_runtime_status()

    def safe_stop(*args: Any, **kwargs: Any) -> dict[str, Any]:
        safe_stops.append(str(kwargs.get("reason")))
        return {"ok": True}

    service._runtime_monitor_status = sample  # type: ignore[method-assign]
    service._safe_stop_internal = safe_stop  # type: ignore[method-assign]
    service._runtime_monitor_worker("internal", service._pair("pair_1"))

    assert samples >= 4
    assert safe_stops == []
    stats = service.runtime_monitor_diagnostics()["pairs"]["pair_1"]
    assert stats["deferred_verifications"] >= 3
    assert stats["verification_recoveries"] == 1
    assert stats["safety_stops"] == 0


def test_runtime_monitor_safe_stops_after_unverified_timeout() -> None:
    service = configured_service()
    service.config.runtime_monitor_interval_seconds = 0.002
    service.config.runtime_monitor_refresh_wait_seconds = 0.001
    service.config.runtime_monitor_max_unverified_seconds = 0.01
    service.config.runtime_monitor_max_consecutive_unverified_samples = 3
    service._update_runtime(
        "pair_1",
        commanded_power_kw=10.0,
        requested_power_kw=10.0,
        requested_direction="discharge",
        run_status="success",
    )

    safe_stops: list[str] = []
    service._runtime_monitor_status = (  # type: ignore[method-assign]
        lambda pair_id, pair: _deferred_runtime_status()
    )

    def safe_stop(*args: Any, **kwargs: Any) -> dict[str, Any]:
        safe_stops.append(str(kwargs.get("reason")))
        return {"ok": True}

    service._safe_stop_internal = safe_stop  # type: ignore[method-assign]
    service._runtime_monitor_worker("internal", service._pair("pair_1"))

    assert len(safe_stops) == 1
    assert "runtime_status_unverified_timeout" in safe_stops[0]
    runtime = service._runtime_snapshot("pair_1")
    assert runtime["run_status"] == "failed"
    assert runtime["monitor_state"] == "failed_unverified_timeout"


def test_all_pair_status_is_cache_only_and_reports_parallel_activity() -> None:
    service = configured_service()
    service.config.pairs[1].enabled = True
    service._runtime["pair_1"]["commanded_power_kw"] = 10.0
    service._runtime["pair_1"]["run_status"] = "success"
    service._runtime["pair_2"]["run_status"] = "running"

    def cached(pair_id: str, pair: Any) -> dict[str, Any]:
        return {
            "pair": pair.model_dump(),
            "runtime": service._runtime_snapshot(pair_id),
            "summary": {},
            "workflow": {},
            "write_gates": {},
            "errors": [],
            "refresh": {"source": "background_poll_cache"},
        }

    service._read_cached_runtime_status = cached  # type: ignore[method-assign]
    result = service.all_pair_status()

    assert result["count"] == 2
    assert result["summary"]["parallel_operation_supported"] is True
    assert result["summary"]["active_pairs"] == ["pair_1"]
    assert result["summary"]["starting_pairs"] == ["pair_2"]


def test_runtime_monitor_status_converts_busy_lane_to_deferred_verification() -> None:
    from app.services.bms_pcs_control import ControlStatusBusyError

    service = configured_service()
    cached = _deferred_runtime_status()
    service._read_cached_runtime_status = (  # type: ignore[method-assign]
        lambda pair_id, pair: cached
    )

    def busy_status(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ControlStatusBusyError("global_refresh_lane_busy")

    service.status = busy_status  # type: ignore[method-assign]
    result = service._runtime_monitor_status("pair_1", service._pair("pair_1"))

    assert result["runtime_verification"]["deferred"] is True
    assert result["runtime_verification"]["reason"] == "refresh_lane_busy"
    assert result["refresh"]["verification_deferred"] is True


def test_global_live_refresh_lane_is_fifo() -> None:
    from app.services.bms_pcs_control import _FairRefreshLane

    lane = _FairRefreshLane()
    assert lane.acquire(blocking=False) is True

    order: list[int] = []
    threads: list[threading.Thread] = []

    def worker(value: int) -> None:
        assert lane.acquire(timeout=1.0) is True
        order.append(value)
        time.sleep(0.002)
        lane.release()

    for value in (1, 2, 3):
        thread = threading.Thread(target=worker, args=(value,))
        thread.start()
        threads.append(thread)
        deadline = time.monotonic() + 1.0
        while lane.diagnostics()["pending_count"] < value:
            assert time.monotonic() < deadline
            time.sleep(0.001)

    lane.release()
    for thread in threads:
        thread.join(timeout=1.0)
        assert not thread.is_alive()

    assert order == [1, 2, 3]
    assert lane.diagnostics() == {
        "policy": "fifo_single_flight",
        "active": False,
        "pending_count": 0,
    }



def test_startup_lane_preserves_fifo_and_allows_queued_abort() -> None:
    lane = control_module._FairRefreshLane()
    assert lane.acquire() is True

    order: list[str] = []
    cancel_second = threading.Event()

    def wait(name: str, cancel: threading.Event | None = None) -> None:
        acquired = lane.acquire(cancel_event=cancel)
        if acquired:
            order.append(name)
            lane.release()
        else:
            order.append(f"{name}:cancelled")

    first = threading.Thread(target=wait, args=("first",))
    second = threading.Thread(target=wait, args=("second", cancel_second))
    third = threading.Thread(target=wait, args=("third",))
    first.start()
    time.sleep(0.01)
    second.start()
    time.sleep(0.01)
    third.start()
    time.sleep(0.02)
    cancel_second.set()
    time.sleep(0.3)
    lane.release()

    first.join(1.0)
    second.join(1.0)
    third.join(1.0)

    assert order == ["second:cancelled", "first", "third"]
    assert lane.diagnostics() == {
        "policy": "fifo_single_flight",
        "active": False,
        "pending_count": 0,
    }

def test_pair_specific_bau_is_used_for_precharge_and_safe_stop() -> None:
    service = configured_service()
    service.config.pairs[2].enabled = True
    service.gateway_config.pcs.devices[2].enabled = True
    service.bms_driver.writes = []
    original_write = service.bms_driver.write_point

    def record(asset_id: str, key: str, value: int) -> dict[str, Any]:
        service.bms_driver.writes.append((asset_id, key, value))
        return original_write(asset_id, key, value)

    service.bms_driver.write_point = record  # type: ignore[method-assign]
    confirm = "EXECUTE_STAGE_WRITE"
    service.start_precharge("internal", "pair_3", confirm)
    assert ("bms_bank_3", "auto_onnected", 1) in service.bms_driver.writes
    assert not any(key == "start_pre_chg_operate" for _, key, _ in service.bms_driver.writes)

    service.safe_stop("internal", "pair_3", confirm, open_bms=True)
    assert ("bms_bank_3", "auto_onnected", 0) in service.bms_driver.writes


def test_cached_status_endpoint_shape_is_full_control_status() -> None:
    service = configured_service()

    def cached(pair_id: str, pair: Any) -> dict[str, Any]:
        return {
            "pair": pair.model_dump(),
            "timestamp": "2026-07-31T00:00:00+00:00",
            "runtime": service._runtime_snapshot(pair_id),
            "summary": {"pcs_actual_power_kw": -100.0},
            "workflow": {"system_state": "charging"},
            "write_gates": {},
            "errors": [],
            "refresh": {"source": "background_poll_cache", "stale": False},
        }

    service._read_cached_runtime_status = cached  # type: ignore[method-assign]
    result = service.status("pair_1", fresh=False)
    assert result["summary"]["pcs_actual_power_kw"] == -100.0
    assert result["workflow"]["system_state"] == "charging"


def test_safe_stop_never_opens_bau_without_verified_zero_and_pcs_stop() -> None:
    service = configured_service()
    writes: list[tuple[str, str, Any]] = []
    original_pcs_write = service.pcs_driver.write_point
    original_bms_write = service.bms_driver.write_point

    def pcs_write(asset_id: str, key: str, value: Any) -> dict[str, Any]:
        writes.append((asset_id, key, value))
        return original_pcs_write(asset_id, key, value)

    def bms_write(asset_id: str, key: str, value: Any) -> dict[str, Any]:
        writes.append((asset_id, key, value))
        return original_bms_write(asset_id, key, value)

    service.pcs_driver.write_point = pcs_write  # type: ignore[method-assign]
    service.bms_driver.write_point = bms_write  # type: ignore[method-assign]
    service._wait_for_status = (  # type: ignore[method-assign]
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("not verified"))
    )

    result = service._safe_stop_internal(
        "internal", service._pair("pair_1"), open_bms=True, reason="test"
    )

    assert result["ok"] is False
    assert result["bms_open_requested"] is False
    assert not any(key == "auto_onnected" for _, key, _ in writes)
    assert any("bau_pair_cut_off_inhibited" in error for error in result["errors"])


def test_safe_stop_all_processes_each_enabled_pair_independently() -> None:
    service = configured_service()
    service.config.pairs[2].enabled = True
    service.gateway_config.pcs.devices[2].enabled = True
    stopped: list[str] = []

    def safe_stop(
        username: str,
        pair: Any,
        *,
        open_bms: bool,
        reason: str,
    ) -> dict[str, Any]:
        stopped.append(pair.pair_id)
        return {"ok": True, "errors": [], "open_bms": open_bms, "reason": reason}

    service._safe_stop_internal = safe_stop  # type: ignore[method-assign]
    result = service.safe_stop_all(
        "internal", "EXECUTE_STAGE_WRITE", open_bms=True
    )

    assert result["ok"] is True
    assert stopped == ["pair_1", "pair_3"]
    assert set(result["results"]) == {"pair_1", "pair_3"}


def test_bau_command_values_are_field_proven_zero_and_one() -> None:
    service = configured_service()
    assert service.config.bau_connect_value == 1
    assert service.config.bau_disconnect_value == 0


def test_compact_all_pair_status_excludes_full_points_and_steps() -> None:
    service = configured_service()

    def cached(pair_id: str, pair: Any) -> dict[str, Any]:
        return {
            "pair": pair.model_dump(),
            "timestamp": "2026-08-01T00:00:00+00:00",
            "runtime": {
                **service._runtime_snapshot(pair_id),
                "steps": [{"key": "large", "result": {"raw": list(range(100))}}],
            },
            "summary": {
                "pcs_actual_power_kw": -2.0,
                "pcs_power_setpoint_kw": -2.0,
                "precharge_state": 3,
                "contactors_ready": True,
            },
            "workflow": {"system_state": "charging", "ready_for_power": True},
            "write_gates": {},
            "points": {"large": {"raw": list(range(100))}},
            "errors": [],
            "refresh": {
                "source": "background_poll_cache",
                "stale": False,
                "freshness": {"pcs": {"age_seconds": 1.2}},
            },
        }

    service._read_cached_runtime_status = cached  # type: ignore[method-assign]
    result = service.all_pair_status_compact()
    pair = result["pairs"][0]
    assert "points" not in pair
    assert "steps" not in pair["runtime"]
    assert pair["summary"]["pcs_actual_power_kw"] == -2.0
    assert pair["refresh"]["cache_age_seconds"] == 1.2


def test_automatic_start_is_queued_and_uses_bounded_executor() -> None:
    service = configured_service()
    service.config.allow_full_automatic_sequence = True
    entered = threading.Event()
    release = threading.Event()

    def worker(*args: Any, **kwargs: Any) -> None:
        entered.set()
        release.wait(1.0)

    service._automatic_worker = worker  # type: ignore[method-assign]
    result = service.automatic_start(
        "internal",
        "pair_1",
        "charge",
        2.0,
        service.config.automatic_confirmation_phrase,
    )
    assert result["accepted"] is True
    assert result["run_status"] == "queued"
    assert result["all_pair_status_endpoint"].endswith("/compact")
    assert entered.wait(1.0)
    release.set()


def test_next_step_and_abort_service_methods_remain_available() -> None:
    service = configured_service()
    assert callable(service.next_step)
    assert callable(service.abort)
