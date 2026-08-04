import json
from pathlib import Path

from app.core.config import GatewayConfig, project_root
from app.services.gateway_service import GatewayService
from app.storage.sqlite_store import SQLiteStore


def make_service(tmp_path: Path) -> GatewayService:
    payload = json.loads((project_root() / "configs/kinetics_mock.json").read_text())
    payload["storage"]["preferred_root"] = str(tmp_path / "storage")
    payload["storage"]["fallback_root"] = str(tmp_path / "fallback")
    config = GatewayConfig.model_validate(payload)
    return GatewayService(config, SQLiteStore(config.storage))


def test_mock_snapshot_all_assets(tmp_path):
    service = make_service(tmp_path)
    snapshot = service.snapshot()
    assert snapshot["bank"]["asset_id"] == "bms_bank"
    assert len(snapshot["racks"]) == 4
    assert "hvac" in snapshot["environment"]
    assert len(snapshot["pcs"]["telemetry"]) == 288
    assert len(service.assets()) >= 12


def test_full_rack_detail_contains_bulk_arrays(tmp_path):
    service = make_service(tmp_path)
    details = service.rack_details(1)
    cell = details["telemetry"].get("vcell")
    assert cell is not None
    assert len(cell["value"]) == 512


def test_scenario_creates_alarm(tmp_path):
    service = make_service(tmp_path)
    service.set_mock_scenario("emergency_stop")
    alarms = service.snapshot()["alarms"]
    assert any("emergency_stop" in alarm["code"] for alarm in alarms)


def test_mock_write_and_audit(tmp_path):
    service = make_service(tmp_path)
    response = service.execute_control("internal", "bms_bank", "reset", 1)
    assert response["ok"] is True
    audit = service.store.list_command_audit()
    assert audit[0]["point_key"] == "reset"
