from pathlib import Path

from app.services.runtime_metrics import RuntimeMetrics


def test_startup_stage_is_bounded_and_reported():
    metrics = RuntimeMetrics()
    metrics.startup_stage("hardware_cache_initialization", 12.3456, ready=True)
    stage = metrics.snapshot()["startup_stages"]["hardware_cache_initialization"]
    assert stage["elapsed_ms"] == 12.346
    assert stage["ready"] is True


def test_database_cache_hint_source_is_advisory():
    source = Path("app/storage/sqlite_store.py").read_text(encoding="utf-8")
    assert "POSIX_FADV_DONTNEED" in source
    assert "os.remove" not in source
