import json
from pathlib import Path

from app.core.config import GatewayConfig, project_root
from app.services.gateway_service import GatewayService
from app.storage.sqlite_store import SQLiteStore


def make_service(tmp_path: Path) -> GatewayService:
    payload = json.loads((project_root() / "configs/kinetics_mock.json").read_text())
    payload["storage"]["preferred_root"] = str(tmp_path / "storage")
    payload["storage"]["fallback_root"] = str(tmp_path / "fallback")
    payload["storage"]["require_preferred_mount"] = False
    config = GatewayConfig.model_validate(payload)
    return GatewayService(config, SQLiteStore(config.storage))


def test_multirate_initialization_contains_every_active_group(tmp_path):
    service = make_service(tmp_path)
    snapshot = service.snapshot()
    assert len(snapshot["bank"]["telemetry"]) == 155
    assert all(len(rack["telemetry"]) == 371 for rack in snapshot["racks"])
    assert sum(len(asset["telemetry"]) for asset in snapshot["environment"].values()) == 131
    assert len(snapshot["pcs"]["telemetry"]) == 288
    for name in ("fast", "normal", "slow", "bulk", "pcs"):
        assert snapshot["polling"][name]["count"] >= 1


def test_delta_updates_are_available_per_poll_class(tmp_path):
    service = make_service(tmp_path)
    sequence = service.snapshot()["sequence"]
    event = service.poll_bms_class("fast")
    assert event["poll_class"] == "fast"
    updates = service.updates_since(sequence)
    assert updates
    assert updates[-1]["sequence"] == event["sequence"]
    assert all("telemetry" in asset for asset in event["assets"])


def test_compact_snapshot_and_data_rate_analysis(tmp_path):
    service = make_service(tmp_path)
    compact = json.dumps(service.compact_snapshot(), separators=(",", ":")).encode()
    full = json.dumps(service.snapshot(), separators=(",", ":")).encode()
    assert len(compact) < len(full)
    analysis = service.data_rate_analysis()
    assert analysis["streaming"]["estimated_bytes_per_minute"] > 0
    assert analysis["storage"]["estimated_days_to_high_watermark"] > 1


def test_compressed_sqlite_round_trip(tmp_path):
    service = make_service(tmp_path)
    rows = service.store.query_telemetry("bms_bank", limit=1)
    assert rows
    assert "telemetry" in rows[0]["payload"]
    status = service.store.status()
    assert status["compression_enabled"] is True
    assert status["telemetry_size"]["stored_bytes_total"] < status["telemetry_size"]["uncompressed_bytes_total"]
