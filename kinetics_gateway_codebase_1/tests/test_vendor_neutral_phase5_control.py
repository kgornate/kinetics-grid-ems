from __future__ import annotations

import time
from typing import Any

from app.core.config import GatewayConfig, PcsDeviceConfig, RackEndpointConfig
from app.services.control_factory import build_pair_control_service
from app.services.vendor_neutral_control import VendorNeutralPairControlService


class FakeStore:
    def __init__(self) -> None:
        self.commands: list[tuple[Any, ...]] = []
        self.events: list[tuple[Any, ...]] = []

    def audit_command(self, *args: Any, **kwargs: Any) -> None:
        self.commands.append(args)

    def event(self, *args: Any, **kwargs: Any) -> None:
        self.events.append(args)


class FakeLineageBms:
    def __init__(self) -> None:
        self.state = 0xBBBB
        self.contactors = 1
        self.fault_reset_value = 0
        self.values = {
            "rack_voltage": 1300.0,
            "rack_current": 10.0,
            "rack_soc": 55.0,
            "rack_soh": 98.0,
            "rack_max_charge_power": 150.0,
            "rack_max_discharge_power": 160.0,
            "rack_max_charge_current": 120.0,
            "rack_max_discharge_current": 125.0,
            "positive_insulation_resistance": 5.0,
            "negative_insulation_resistance": 5.0,
        }

    def read_point(self, asset_id: str, key: str) -> dict[str, Any]:
        if asset_id == "bms_bank":
            bank = {
                "battery_system_state": self.state,
                "system_max_charge_power": 300.0,
                "system_max_discharge_power": 320.0,
                "system_max_charge_current": 240.0,
                "system_max_discharge_current": 250.0,
                "system_soc": 55.0,
                "system_soh": 98.0,
            }
            return {"value": bank[key], "raw": bank[key]}
        rack = {
            "rack_state": self.state,
            "rack_operating_state": 2,
            "positive_contactor_feedback": self.contactors,
            "negative_contactor_feedback": self.contactors,
            **self.values,
        }
        return {"value": rack[key], "raw": rack[key]}

    def write_point(self, asset_id: str, key: str, value: Any) -> dict[str, Any]:
        if key == "fault_reset":
            self.fault_reset_value = int(value)
            if value == 1:
                self.state = 0xBBBB
        elif key in {"positive_contactor_command", "negative_contactor_command"} and int(value) == 2:
            self.contactors = 0
        return {
            "ok": True,
            "asset_id": asset_id,
            "point_key": key,
            "written_value": value,
            "readback": {"value": value},
        }


class FakeElecodPcs:
    def __init__(self) -> None:
        self.running = False
        self.faulted = False
        self.setpoint_percent = 0.0
        self.reactive_percent = 0.0
        self.grid_mode = 0
        self.on_grid_mode = 0
        self.reactive_mode = 2
        self.standby_value = None

    def device(self, asset_id: str):
        return PcsDeviceConfig(asset_id=asset_id, unit_id=1, enabled=True, rated_power_kw=215.0)

    def read_point(self, asset_id: str, key: str) -> dict[str, Any]:
        status = 0
        if self.running:
            status |= 1 << 6
            status |= 1 << 2
            status |= 1 << 3
        if self.faulted:
            status |= 1 << 7
        values = {
            "status_word": status,
            "total_active_power": self.setpoint_percent * 215.0 / 100.0,
            "total_reactive_power": self.reactive_percent * 215.0 / 100.0,
            "dc_voltage": 1300.0,
            "dc_current": 20.0,
            "dc_bus_voltage": 1300.0,
            "active_power_setpoint_percent": self.setpoint_percent,
        }
        value = values[key]
        return {"value": value, "raw": value, "point_key": key}

    def write_point(self, asset_id: str, key: str, value: Any) -> dict[str, Any]:
        if key == "active_power_setpoint_percent":
            self.setpoint_percent = float(value)
        elif key == "reactive_power_setpoint_percent":
            self.reactive_percent = float(value)
        elif key == "grid_mode_command":
            self.grid_mode = int(value)
        elif key == "on_grid_control_mode":
            self.on_grid_mode = int(value)
        elif key == "reactive_mode":
            self.reactive_mode = int(value)
        elif key == "power_on_off_command":
            self.running = int(value) == 0xFF00
        elif key == "standby_shutdown_command":
            self.standby_value = int(value)
        return {
            "ok": True,
            "asset_id": asset_id,
            "point_key": key,
            "written_value": value,
            "readback": {"value": value},
        }


def config() -> GatewayConfig:
    cfg = GatewayConfig()
    cfg.mode = "control_enabled"
    cfg.bms.vendor = "lineage"
    cfg.bms.architecture = "system_rack"
    cfg.bms.write_enabled = True
    cfg.bms.addressing_validated = True
    cfg.bms.float_word_order_validated = True
    cfg.bms.current_sign_validated = True
    cfg.bms.automatic_precharge_validated = True
    cfg.bms.forced_disconnect_sequence_validated = True
    cfg.bms.racks = [RackEndpointConfig(rack_id=1, port=502, unit_id=2)]
    cfg.pcs.vendor = "elecod"
    cfg.pcs.transport = "tcp"
    cfg.pcs.write_enabled = True
    cfg.pcs.addressing_validated = True
    cfg.pcs.start_stop_validated = True
    cfg.pcs.ready_status_validated = True
    cfg.pcs.power_sign_validated = True
    cfg.pcs.positive_power_is_discharge = True
    cfg.pcs.devices = [
        PcsDeviceConfig(asset_id="pcs_1", unit_id=1, enabled=True, rated_power_kw=215.0)
    ]
    cfg.control_sequence.enabled = True
    cfg.control_sequence.allow_full_automatic_sequence = True
    cfg.control_sequence.pairs = [cfg.control_sequence.pairs[0]]
    cfg.control_sequence.pairs[0].enabled = True
    cfg.control_sequence.valid_samples_required = 1
    cfg.control_sequence.sample_interval_seconds = 0.001
    cfg.control_sequence.pcs_start_timeout_seconds = 0.1
    cfg.control_sequence.power_tracking_timeout_seconds = 0.1
    cfg.control_sequence.runtime_monitor_enabled = False
    cfg.control_sequence.require_precharge_success = False
    cfg.control_sequence.bms_rack_voltage_min_v = 1000.0
    cfg.control_sequence.bms_rack_voltage_max_v = 1500.0
    cfg.control_sequence.pcs_dc_bus_voltage_min_v = 1000.0
    cfg.control_sequence.pcs_dc_bus_voltage_max_v = 1500.0
    return cfg


def service() -> VendorNeutralPairControlService:
    cfg = config()
    return VendorNeutralPairControlService(cfg, FakeLineageBms(), FakeElecodPcs(), FakeStore())


def test_factory_selects_vendor_neutral_controller_for_lineage_elecod() -> None:
    cfg = config()
    result = build_pair_control_service(cfg, FakeLineageBms(), FakeElecodPcs(), FakeStore())
    assert isinstance(result, VendorNeutralPairControlService)


def test_real_hardware_control_is_blocked_until_field_validation_gates_are_confirmed() -> None:
    cfg = config()
    cfg.bms.float_word_order_validated = False
    svc = VendorNeutralPairControlService(cfg, FakeLineageBms(), FakeElecodPcs(), FakeStore())
    try:
        svc.configure_pcs("internal", "pair_1", "EXECUTE_STAGE_WRITE")
    except PermissionError as error:
        assert "FLOAT word order" in str(error)
    else:
        raise AssertionError("Expected positive field-validation gate")


def test_staged_lineage_elecod_charge_discharge_path() -> None:
    svc = service()
    confirm = "EXECUTE_STAGE_WRITE"
    # PCS configuration is possible before PCS start and always forces zero power.
    assert svc.configure_pcs("internal", "pair_1", confirm)["ok"] is True
    assert svc.start_precharge("internal", "pair_1", confirm)["ok"] is True
    assert svc.start_pcs("internal", "pair_1", confirm)["ok"] is True
    assert svc.verify_ready("pair_1")["ok"] is True
    precheck = svc.precheck("pair_1", "discharge", 50.0)
    assert precheck["ok"] is True
    assert precheck["effective_power_limit_kw"] == 160.0
    result = svc.set_power("internal", "pair_1", "discharge", 50.0, confirm)
    assert result["commanded_signed_power_kw"] == 50.0
    verified = svc.verify_power("pair_1")
    assert round(float(verified["setpoint"]["value"]), 3) == 50.0
    assert round(float(verified["actual_power"]["value"]), 3) == 50.0
    stopped = svc.safe_stop("internal", "pair_1", confirm, open_bms=False)
    assert stopped["ok"] is True


def test_charge_uses_negative_gateway_sign_but_driver_conversion_is_hidden() -> None:
    svc = service()
    confirm = "EXECUTE_STAGE_WRITE"
    svc.configure_pcs("internal", "pair_1", confirm)
    svc.start_pcs("internal", "pair_1", confirm)
    result = svc.set_power("internal", "pair_1", "charge", 43.0, confirm)
    assert result["commanded_signed_power_kw"] == -43.0
    assert round(result["write"]["vendor_percent"], 3) == -20.0


def test_dynamic_bms_limit_blocks_requested_power_above_rack_limit() -> None:
    svc = service()
    svc.configure_pcs("internal", "pair_1", "EXECUTE_STAGE_WRITE")
    svc.start_pcs("internal", "pair_1", "EXECUTE_STAGE_WRITE")
    result = svc.precheck("pair_1", "charge", 151.0)
    assert result["ok"] is False
    assert result["checks"]["requested_power_within_dynamic_bms_limit"] is False
    assert result["effective_power_limit_kw"] == 150.0


def test_power_sign_validation_is_a_hard_nonzero_control_gate() -> None:
    cfg = config()
    cfg.pcs.power_sign_validated = False
    svc = VendorNeutralPairControlService(cfg, FakeLineageBms(), FakeElecodPcs(), FakeStore())
    svc.configure_pcs("internal", "pair_1", "EXECUTE_STAGE_WRITE")
    svc.start_pcs("internal", "pair_1", "EXECUTE_STAGE_WRITE")
    result = svc.precheck("pair_1", "discharge", 10.0)
    assert result["ok"] is False
    assert result["checks"]["elecod_power_sign_validated"] is False


def test_lineage_warning_blocks_power_by_default() -> None:
    cfg = config()
    bms = FakeLineageBms()
    bms.state = 0xCCCC
    svc = VendorNeutralPairControlService(cfg, bms, FakeElecodPcs(), FakeStore())
    state = svc.battery.rack_state(1)
    assert state.charge_allowed is False
    assert state.discharge_allowed is False


def test_automatic_sequence_completes_in_simulated_healthy_environment() -> None:
    svc = service()
    accepted = svc.automatic_start(
        "internal",
        "pair_1",
        "discharge",
        20.0,
        "EXECUTE_AUTOMATIC_SEQUENCE",
        ramp_step_kw=10.0,
        ramp_interval_seconds=0.001,
    )
    assert accepted["accepted"] is True
    deadline = time.time() + 1.0
    while time.time() < deadline:
        runtime = svc._runtime_snapshot("pair_1")
        if runtime["run_status"] in {"success", "failed"}:
            break
        time.sleep(0.005)
    runtime = svc._runtime_snapshot("pair_1")
    assert runtime["run_status"] == "success", runtime
    assert runtime["commanded_power_kw"] == 20.0
