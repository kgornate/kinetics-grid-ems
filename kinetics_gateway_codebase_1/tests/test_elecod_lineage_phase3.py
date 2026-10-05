from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.assets.elecod_adapter import ElecodPcsAdapter
from app.assets.lineage_adapter import LineageBmsAdapter
from app.core.catalog import ProtocolCatalog
from app.core.config import GatewayConfig, PcsConfig, PcsDeviceConfig, project_root
from app.protocols.codec import decode_point, encode_scalar


class FakeLineageDriver:
    def __init__(self, values: dict[str, float | int]) -> None:
        self.values = values
        self.writes: list[tuple[str, str, float | int]] = []

    def read_point(self, asset_id: str, key: str):
        if key not in self.values:
            raise KeyError(key)
        return {"value": self.values[key], "raw": self.values[key], "asset_id": asset_id, "point_key": key}

    def write_point(self, asset_id: str, key: str, value: float | int):
        self.writes.append((asset_id, key, value))
        return {"ok": True, "asset_id": asset_id, "point_key": key, "written_value": value}


class FakeElecodDriver:
    def __init__(self) -> None:
        self.writes: list[tuple[str, str, float | int]] = []

    def write_point(self, asset_id: str, key: str, value: float | int):
        self.writes.append((asset_id, key, value))
        return {"ok": True, "asset_id": asset_id, "point_key": key, "written_value": value}

    def read_point(self, asset_id: str, key: str):
        values = {
            "status_word": {"value": 0, "raw": (1 << 2) | (1 << 3) | (1 << 6)},
            "total_active_power": {"value": 42.5, "raw": 425},
            "total_reactive_power": {"value": 1.2, "raw": 12},
            "dc_voltage": {"value": 1200.0, "raw": 12000},
            "dc_current": {"value": 35.0, "raw": 350},
            "dc_bus_voltage": {"value": 1195.0, "raw": 11950},
        }
        return {**values[key], "asset_id": asset_id, "point_key": key}


def _normal_lineage_values() -> dict[str, float | int]:
    return {
        "rack_state": 0xBBBB,
        "rack_operating_state": 2,
        "rack_voltage": 1210.0,
        "rack_current": 0.0,
        "rack_soc": 58.0,
        "rack_soh": 98.0,
        "rack_max_charge_power": 150.0,
        "rack_max_discharge_power": 180.0,
        "rack_max_charge_current": 125.0,
        "rack_max_discharge_current": 150.0,
        "positive_contactor_feedback": 1,
        "negative_contactor_feedback": 1,
        "positive_insulation_resistance": 5.2,
        "negative_insulation_resistance": 5.1,
    }


def test_lineage_catalog_contains_control_critical_points():
    catalog = ProtocolCatalog.load(project_root() / "generated_protocols/lineage_bms_catalog.json")
    assert len(catalog.points) == 3527
    expected = {
        ("bank", "battery_system_state"),
        ("bank", "system_max_charge_power"),
        ("bank", "system_max_discharge_power"),
        ("rack", "rack_state"),
        ("rack", "rack_voltage"),
        ("rack", "rack_max_charge_power"),
        ("rack", "rack_max_discharge_power"),
        ("rack", "positive_contactor_feedback"),
        ("rack", "negative_contactor_feedback"),
        ("bank", "fault_reset"),
    }
    for scope, key in expected:
        assert catalog.by_key(key, scope=scope) is not None, (scope, key)


def test_elecod_catalog_contains_control_critical_points():
    catalog = ProtocolCatalog.load(project_root() / "generated_protocols/elecod_pcs_catalog.json")
    assert len(catalog.points) == 391
    for key in (
        "total_active_power",
        "dc_voltage",
        "dc_current",
        "dc_bus_voltage",
        "status_word",
        "active_power_setpoint_percent",
        "grid_mode_command",
        "on_grid_control_mode",
        "off_grid_control_mode",
        "power_on_off_command",
        "standby_shutdown_command",
    ):
        assert catalog.by_key(key, scope="pcs") is not None, key


def test_lineage_normal_rack_maps_to_vendor_neutral_state_and_readiness():
    adapter = LineageBmsAdapter(FakeLineageDriver(_normal_lineage_values()))  # type: ignore[arg-type]
    state = adapter.rack_state(1)
    assert state.state_label == "Normal"
    assert state.charge_allowed is True
    assert state.discharge_allowed is True
    assert state.max_charge_power_kw == 150.0
    assert state.max_discharge_power_kw == 180.0
    assert state.positive_contactor_closed is True
    assert state.negative_contactor_closed is True
    preparation = adapter.prepare_for_operation(1)
    assert preparation.ok is True
    assert preparation.command_issued is False
    assert preparation.state == "ready"


def test_lineage_no_charge_state_blocks_charge_without_inventing_precharge_write():
    values = _normal_lineage_values()
    values["rack_state"] = 0x1111
    values["positive_contactor_feedback"] = 0
    values["negative_contactor_feedback"] = 0
    driver = FakeLineageDriver(values)
    adapter = LineageBmsAdapter(driver)  # type: ignore[arg-type]
    state = adapter.rack_state(2)
    assert state.charge_allowed is False
    assert state.discharge_allowed is True
    preparation = adapter.prepare_for_operation(2)
    assert preparation.ok is False
    assert preparation.command_issued is False
    assert preparation.state == "waiting_for_bms_automatic_precharge"
    assert driver.writes == []


def test_lineage_forced_contactor_disconnect_is_gated_by_default():
    driver = FakeLineageDriver(_normal_lineage_values())
    adapter = LineageBmsAdapter(driver)  # type: ignore[arg-type]
    result = adapter.disconnect(1)
    assert result.ok is False
    assert result.state == "capability_gated"
    assert driver.writes == []


def test_elecod_kw_conversion_and_hardware_sign_gate():
    driver = FakeElecodDriver()
    guarded = ElecodPcsAdapter(driver, rated_power_kw=215.0, power_sign_validated=False)  # type: ignore[arg-type]
    with pytest.raises(PermissionError):
        guarded.set_active_power_kw("pcs_1", 107.5)
    assert driver.writes == []

    adapter = ElecodPcsAdapter(driver, rated_power_kw=215.0, power_sign_validated=True)  # type: ignore[arg-type]
    result = adapter.set_active_power_kw("pcs_1", 107.5)
    assert result["vendor_percent"] == pytest.approx(50.0)
    assert driver.writes[-1] == ("pcs_1", "active_power_setpoint_percent", pytest.approx(50.0))


def test_elecod_status_word_maps_to_normalized_state():
    adapter = ElecodPcsAdapter(FakeElecodDriver(), rated_power_kw=215.0)  # type: ignore[arg-type]
    state = adapter.state("pcs_1")
    assert state.running is True
    assert state.dc_relay_connected is True
    assert state.ac_relay_connected is True
    assert state.faulted is False
    assert state.actual_active_power_kw == 42.5


def test_codec_supports_scale_plus_offset_for_lineage_auxiliary_setpoints():
    words = encode_scalar(25.0, "U16", scale=0.01, offset=-100.0)
    assert words == [12500]
    point = {"data_type": "U16", "register_width": 1, "element_count": 1, "scale": 0.01, "offset": -100.0}
    decoded = decode_point(point, words)
    assert decoded["value"] == pytest.approx(25.0)


def test_tcp_configuration_allows_same_unit_id_on_different_endpoints():
    config = PcsConfig(
        transport="tcp",
        devices=[
            PcsDeviceConfig(asset_id="pcs_1", host="192.0.2.21", port=502, unit_id=1),
            PcsDeviceConfig(asset_id="pcs_2", host="192.0.2.22", port=502, unit_id=1),
        ],
    )
    assert len(config.enabled_devices) == 2


def test_tcp_configuration_rejects_duplicate_endpoint_and_unit_route():
    with pytest.raises(ValidationError):
        PcsConfig(
            transport="tcp",
            devices=[
                PcsDeviceConfig(asset_id="pcs_1", host="192.0.2.21", port=502, unit_id=1),
                PcsDeviceConfig(asset_id="pcs_2", host="192.0.2.21", port=502, unit_id=1),
            ],
        )


def test_phase3_config_template_loads_with_writes_disabled():
    from app.core.config import load_config

    config = load_config("configs/elecod_lineage_4pair_phase3_template.json")
    assert config.mode == "read_only"
    assert config.bms.write_enabled is False
    assert config.pcs.write_enabled is False
    assert config.control_sequence.enabled is False
    assert config.bms_catalog_file.endswith("lineage_bms_catalog.json")
    assert config.pcs_catalog_file.endswith("elecod_pcs_catalog.json")
    assert [p.pair_id for p in config.control_sequence.pairs] == ["pair_1", "pair_2", "pair_3", "pair_4"]
