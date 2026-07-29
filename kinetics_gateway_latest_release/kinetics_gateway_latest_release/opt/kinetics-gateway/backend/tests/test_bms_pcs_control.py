from __future__ import annotations

from typing import Any

from app.core.config import GatewayConfig, PcsDeviceConfig
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
            "vrack": {"value": 1389.0},
            "irack_chg_limit": {"value": 200.0},
            "irack_dsg_limit": {"value": 200.0},
            "pre_charge_state": {"value": 3 if self.precharge else 0},
            "start_pre_chg_operate": {"value": self.precharge},
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
        if key == "start_pre_chg_operate":
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
            "operating_state": self.state,
            "grid_active_power": self.values["active_power_setpoint"],
            **self.values,
        }
        return {"value": values[key], "point_key": key}

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
    assert service.precheck("pair_1", "discharge", 10.0)["ok"] is True
    assert service.enable_rack("internal", "pair_1", "discharge", 10.0, confirm)["ok"] is True
    assert service.start_precharge("internal", "pair_1", confirm)["ok"] is True
    assert service.verify_ready("pair_1")["ok"] is True
    assert service.configure_pcs("internal", "pair_1", confirm)["ok"] is True
    assert service.start_pcs("internal", "pair_1", confirm)["ok"] is True
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
    assert [action["written_value"] for action in result["actions"]] == [1, 0]
    assert service.bms_driver.recovery_value == 0


def test_bms_recovery_is_blocked_if_rack_is_enabled() -> None:
    service = configured_service()
    service.bms_driver.system_fault = True
    service.bms_driver.rack_enabled = 1
    try:
        service.recover_bms("internal", "pair_1", "EXECUTE_STAGE_WRITE")
    except ValueError as error:
        assert "rack_disabled" in str(error)
    else:
        raise AssertionError("Recovery should be blocked while the rack is enabled")
