from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import GatewayConfig, load_config, project_root
from app.services.gateway_service import GatewayService
from app.services.normalized_views import build_normalized_snapshot
from app.services.platform_readiness import platform_readiness
from app.storage.sqlite_store import SQLiteStore


def pt(value):
    return {"value": value, "raw": value, "quality": "good", "bitfields": {}}


def test_control_ready_template_is_software_complete_but_field_locked() -> None:
    cfg = load_config("configs/elecod_lineage_4pair_control_ready_template.json")
    result = platform_readiness(cfg)
    assert result["software_status"] == "software_complete_field_validation_pending"
    assert result["software_scope"]["automatic_charge_discharge_sequence"] is True
    assert result["field_validation"]["complete"] is False
    assert result["hardware_control_armed"] is False
    assert result["automatic_control_armed"] is False
    assert "Lineage FLOAT32 word order" in result["field_validation"]["critical_pending"]
    assert "Elecod active-power sign convention" in result["field_validation"]["critical_pending"]


def test_sil_runs_control_without_claiming_field_validation() -> None:
    cfg = load_config("configs/elecod_lineage_4pair_sil.json")
    result = platform_readiness(cfg)
    assert cfg.mode == "mock"
    assert result["software_scope"]["pair_control_state_machine"] is True
    assert result["field_validation"]["complete"] is False
    assert result["hardware_control_armed"] is False


def test_lineage_warn_is_conservatively_blocked_in_normalized_pair_view() -> None:
    cfg = load_config("configs/elecod_lineage_4pair_control_ready_template.json")
    snapshot = {
        "gateway_id": "g",
        "timestamp": "t",
        "sequence": 1,
        "bank": {"asset_id": "bms_bank", "online": True, "telemetry": {"battery_system_state": pt(0xCCCC)}},
        "racks": [{
            "asset_id": "bms_rack_1",
            "rack_id": 1,
            "online": True,
            "telemetry": {
                "rack_state": pt(0xCCCC),
                "rack_operating_state": pt(2),
                "rack_voltage": pt(1300.0),
                "rack_max_charge_power": pt(100.0),
                "rack_max_discharge_power": pt(100.0),
            },
        }],
        "pcs_devices": {},
        "environment": {},
    }
    view = build_normalized_snapshot(snapshot, cfg)
    rack = view["battery_racks"]["1"]
    assert rack["charge_allowed"] is False
    assert rack["discharge_allowed"] is False
    assert "bms_warning_vendor_policy_required" in rack["blocking_reasons"]


def test_generic_raw_api_cannot_bypass_elecod_or_lineage_pair_safety(tmp_path: Path) -> None:
    payload = json.loads((project_root() / "configs/elecod_lineage_4pair_sil.json").read_text())
    payload["storage"]["preferred_root"] = str(tmp_path / "storage")
    payload["storage"]["fallback_root"] = str(tmp_path / "fallback")
    cfg = GatewayConfig.model_validate(payload)
    service = GatewayService(cfg, SQLiteStore(cfg.storage))
    with pytest.raises(PermissionError, match="protected"):
        service.execute_control("internal", "pcs_1", "active_power_setpoint_percent", 10)
    with pytest.raises(PermissionError, match="protected from the generic"):
        service.execute_control("internal", "bms_rack_1", "positive_contactor_command", 2)
