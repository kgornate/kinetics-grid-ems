import json
import threading
import time
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


def test_lightweight_diagnostics_use_cached_data(tmp_path, monkeypatch):
    service = make_service(tmp_path)

    def unexpected_live_storage_call():
        raise AssertionError("lightweight endpoints must not query SQLite live")

    monkeypatch.setattr(service.store, "status", unexpected_live_storage_call)
    assert service.health()["startup"]["ready"] is True
    assert service.polling_diagnostics()["polling"]["fast"]["count"] >= 1
    storage = service.storage_status()
    assert storage["root"]
    assert storage["database"]
    assert service.data_rate_analysis()["generated_at"]


def test_deferred_initialization_starts_with_bounded_empty_cache(tmp_path):
    payload = json.loads((project_root() / "configs/kinetics_mock.json").read_text())
    payload["storage"]["preferred_root"] = str(tmp_path / "storage")
    payload["storage"]["fallback_root"] = str(tmp_path / "fallback")
    payload["storage"]["require_preferred_mount"] = False
    config = GatewayConfig.model_validate(payload)
    service = GatewayService(
        config,
        SQLiteStore(config.storage),
        eager_initialization=False,
    )
    assert service.initialization_status()["ready"] is False
    assert service.snapshot()["sequence"] == 0
    service.initialize()
    assert service.initialization_status()["ready"] is True
    assert service.snapshot()["sequence"] > 0


def test_rack_summary_omits_large_telemetry_maps(tmp_path):
    service = make_service(tmp_path)
    summary = service.rack_summaries()
    assert summary["count"] == len(service.config.bms.racks)
    assert all("telemetry" not in rack for rack in summary["racks"])
    assert all(rack["telemetry_point_count"] > 0 for rack in summary["racks"])


def test_historian_write_does_not_hold_gateway_cache_lock(tmp_path, monkeypatch):
    service = make_service(tmp_path)
    write_entered = threading.Event()
    release_write = threading.Event()
    original_write = service.store.store_telemetry_batch

    def blocked_write(samples):
        write_entered.set()
        assert release_write.wait(timeout=5), "test did not release historian write"
        return original_write(samples)

    monkeypatch.setattr(service.store, "store_telemetry_batch", blocked_write)
    service._last_store_at = 0.0
    worker = threading.Thread(target=service.poll_bms_class, args=("fast",), daemon=True)
    worker.start()
    assert write_entered.wait(timeout=5), "historian write was not reached"

    started = time.perf_counter()
    summary = service.rack_summaries()
    elapsed = time.perf_counter() - started

    assert summary["count"] == len(service.config.bms.racks)
    assert elapsed < 0.5, "cached read waited behind historian compression/SQLite work"

    release_write.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
