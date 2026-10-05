from __future__ import annotations

from copy import deepcopy

from app.assets.bms_driver import BmsModbusDriver
from app.core.catalog import ProtocolCatalog
from app.core.config import BmsAuxEndpointConfig, GatewayConfig, load_config, project_root
from app.services.alarm_engine import AlarmEngine
from app.services.gateway_service import GatewayService
from app.services.normalized_views import build_normalized_snapshot


def pt(value, *, raw=None, category=None, name_en=None):
    return {
        "value": value,
        "raw": value if raw is None else raw,
        "quality": "good",
        "bitfields": {},
        "category": category,
        "name_en": name_en,
    }


def test_phase4_readonly_template_is_safe_and_vendor_bound():
    config = load_config("configs/elecod_lineage_4pair_phase4_readonly_template.json")
    assert config.mode == "read_only"
    assert config.bms.vendor == "lineage"
    assert config.bms.architecture == "system_rack"
    assert config.bms.write_enabled is False
    assert config.bms.poll_environment_enabled is False
    assert config.pcs.vendor == "elecod"
    assert config.pcs.write_enabled is False
    assert config.control_sequence.enabled is False
    assert [item.rated_power_kw for item in config.pcs.devices] == [215.0] * 4


def test_lineage_system_rack_driver_has_one_system_endpoint_not_four_duplicate_banks():
    config = load_config("configs/elecod_lineage_4pair_phase4_readonly_template.json")
    catalog = ProtocolCatalog.load(project_root() / "generated_protocols/lineage_bms_catalog.json")
    driver = BmsModbusDriver(config.bms, catalog)
    assert "bms_bank" in driver.endpoints
    assert "bms_bank_1" not in driver.endpoints
    assert {f"bms_rack_{index}" for index in range(1, 5)}.issubset(driver.endpoints)


def test_lineage_auxiliary_endpoint_can_be_bound_by_category_without_code_change():
    config = load_config("configs/elecod_lineage_4pair_phase4_readonly_template.json")
    config.bms.poll_environment_enabled = True
    config.bms.auxiliary_devices = [
        BmsAuxEndpointConfig(asset_id="chiller_1", category="chiller", port=502, unit_id=101, read_function_fallback=False)
    ]
    catalog = ProtocolCatalog.load(project_root() / "generated_protocols/lineage_bms_catalog.json")
    driver = BmsModbusDriver(config.bms, catalog)
    endpoint = driver.endpoints["chiller_1"]
    assert endpoint.scope == "environment"
    assert endpoint.categories == ("chiller",)
    assert driver.environment_asset_ids == ["chiller_1"]


def test_phase4_hardware_poll_reads_lineage_system_once_and_each_rack_once():
    config = load_config("configs/elecod_lineage_4pair_phase4_readonly_template.json")

    class FakeDriver:
        environment_asset_ids = ["bms_environment"]

        def __init__(self):
            self.calls = []

        def read_asset_classes(self, asset_id, poll_classes):
            self.calls.append((asset_id, tuple(sorted(poll_classes))))
            return {"asset_id": asset_id, "asset_type": "x", "online": True, "telemetry": {}}

    service = GatewayService.__new__(GatewayService)
    service.config = config
    service.bms_driver = FakeDriver()
    updates = service._hardware_bms_class("fast")
    assert [call[0] for call in service.bms_driver.calls] == [
        "bms_bank", "bms_rack_1", "bms_rack_2", "bms_rack_3", "bms_rack_4"
    ]
    assert len(updates) == 5


def test_normalized_phase4_snapshot_maps_lineage_elecold_pair_without_fieldbus_io():
    config = load_config("configs/elecod_lineage_4pair_phase4_readonly_template.json")
    snapshot = {
        "gateway_id": "g1",
        "timestamp": "t",
        "sequence": 9,
        "bank": {
            "asset_id": "bms_bank",
            "online": True,
            "telemetry": {
                "battery_system_state": pt(0xBBBB),
                "system_voltage": pt(1210.0),
                "system_current": pt(10.0),
                "system_soc": pt(55.0),
                "system_soh": pt(98.0),
                "system_max_charge_power": pt(120.0),
                "system_max_discharge_power": pt(160.0),
                "system_max_charge_current": pt(100.0),
                "system_max_discharge_current": pt(130.0),
            },
        },
        "racks": [],
        "pcs_devices": {},
        "environment": {},
    }
    for index in range(1, 5):
        snapshot["racks"].append({
            "asset_id": f"bms_rack_{index}",
            "rack_id": index,
            "online": True,
            "telemetry": {
                "rack_state": pt(0xBBBB),
                "rack_operating_state": pt(2),
                "rack_voltage": pt(1200 + index),
                "rack_current": pt(0.0),
                "rack_soc": pt(50 + index),
                "rack_soh": pt(99.0),
                "rack_max_charge_power": pt(100.0),
                "rack_max_discharge_power": pt(150.0),
                "rack_max_charge_current": pt(90.0),
                "rack_max_discharge_current": pt(120.0),
                "positive_contactor_feedback": pt(1),
                "negative_contactor_feedback": pt(1),
            },
        })
        snapshot["pcs_devices"][f"pcs_{index}"] = {
            "asset_id": f"pcs_{index}",
            "online": True,
            "telemetry": {
                "status_word": {**pt((1 << 2) | (1 << 3) | (1 << 6)), "bitfields": {}},
                "total_active_power": pt(25.0),
                "total_reactive_power": pt(0.0),
                "dc_voltage": pt(1200.0),
                "dc_current": pt(20.0),
                "dc_power": pt(24.0),
                "dc_bus_voltage": pt(1198.0),
            },
        }
    normalized = build_normalized_snapshot(snapshot, config)
    assert normalized["battery_system"]["state"] == "Normal"
    assert normalized["battery_racks"]["1"]["charge_allowed"] is True
    assert normalized["pcs"]["pcs_1"]["running"] is True
    assert normalized["pairs"]["pair_1"]["online"] is True
    assert normalized["pairs"]["pair_1"]["charge_available_kw"] == 100.0
    assert normalized["pairs"]["pair_1"]["discharge_available_kw"] == 150.0


def test_lineage_direct_discrete_alarms_are_promoted_without_treating_switch_state_as_alarm():
    engine = AlarmEngine()
    asset = {
        "asset_id": "bms_bank",
        "asset_type": "bms_bank",
        "online": True,
        "telemetry": {
            "fire_start": pt(1, category="system_alarm", name_en="Fire start"),
            "ems_communication_fault": pt(1, category="system_alarm", name_en="EMS communication fault"),
            "dc_combiner_busbar_switch_state": pt(1, category="system_alarm", name_en="State of busbar switch at DC Combiner"),
        },
    }
    alarms = engine.extract(asset)
    codes = {alarm["code"] for alarm in alarms}
    assert "fire_start" in codes
    assert "ems_communication_fault" in codes
    assert "dc_combiner_busbar_switch_state" not in codes
    fire = next(alarm for alarm in alarms if alarm["code"] == "fire_start")
    assert fire["severity"] == "critical"
