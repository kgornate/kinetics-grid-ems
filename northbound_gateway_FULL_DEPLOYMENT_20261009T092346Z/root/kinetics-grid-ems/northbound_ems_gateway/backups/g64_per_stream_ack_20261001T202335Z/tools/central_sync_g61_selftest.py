from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

from nb_ems_gateway.central_sync.config import load_central_sync_config
from nb_ems_gateway.central_sync.contracts import make_message
from nb_ems_gateway.central_sync.outbox import OutboxStore
from nb_ems_gateway.central_sync.overflow_archiver import OverflowArchiver


def add_old_message(store: OutboxStore, i: int) -> None:
    seq = store.next_sequence("general_asset_telemetry", "bms_extended")
    msg = make_message(
        schema_version="1.0",
        gateway_id="gw-test",
        site_id="site-test",
        stream="general_asset_telemetry",
        substream="bms_extended",
        sequence=seq,
        priority="P3",
        records=[{"i": i, "blob": "x" * 4096}],
        created_at_utc="2026-09-30T00:00:00Z",
    )
    assert store.enqueue(msg)


def main() -> None:
    cfg0 = load_central_sync_config("configs/central_sync.json")
    version = cfg0.identity.software_version
    assert version in {
        "central-sync-g6.1-live-backlog-isolation",
        "central-sync-g6.2-live-concurrent",
        "central-sync-g6.3-fair-single-worker",
    }, version
    if version == "central-sync-g6.1-live-backlog-isolation":
        assert cfg0.uploader.max_messages_per_request == 50
        assert cfg0.uploader.max_request_bytes == 2 * 1024 * 1024
    elif version == "central-sync-g6.2-live-concurrent":
        assert cfg0.uploader.max_messages_per_request == 25
        assert cfg0.uploader.max_request_bytes == 128 * 1024
        assert cfg0.uploader.worker_count == 4
    else:
        assert cfg0.uploader.max_messages_per_request == 25
        assert cfg0.uploader.max_request_bytes == 128 * 1024
        assert cfg0.uploader.worker_count == 1
        assert cfg0.uploader.fair_batching_enabled is True
    assert cfg0.backend.timeout_sec == 30.0
    assert cfg0.backlog_replay.enabled is False
    assert cfg0.overflow_archive.min_archive_free_space_mb >= 1

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        live_db = root / "live.db"
        archive_dir = root / "archives"
        status_dir = root / "status"
        status_dir.mkdir()

        cfg = cfg0.model_copy(deep=True)
        cfg.outbox.path = str(live_db)
        cfg.outbox.required_mount_path = None
        cfg.outbox.fail_if_mount_missing = False
        cfg.outbox.min_free_space_mb = 0
        cfg.outbox.max_db_size_mb = 128
        cfg.overflow_archive.archive_dir = str(archive_dir)
        cfg.overflow_archive.status_file = str(status_dir / "overflow.json")
        cfg.overflow_archive.high_watermark_mb = 64
        cfg.overflow_archive.target_watermark_mb = 32
        cfg.overflow_archive.spill_min_age_sec = 0.01
        cfg.overflow_archive.min_archive_free_space_mb = 1
        cfg.overflow_archive.max_messages_per_cycle = 10
        cfg.overflow_archive.max_bytes_per_cycle = 512 * 1024
        cfg.overflow_archive.max_chunks_per_check = 4

        live = OutboxStore(
            str(live_db),
            max_db_size_mb=128,
            min_free_space_mb=0,
            fail_if_mount_missing=False,
        )
        add_old_message(live, 1)
        before = live.stats(max_age_sec=0)["unacked_count"]
        assert before == 1
        assert live.sqlite_space_status()["logical_used_bytes"] < 64 * 1024 * 1024

        archiver = OverflowArchiver(config=cfg, outbox=live)
        result = archiver.run_once()
        assert result["spilled"] is True, result
        assert "age" in str(result.get("trigger")), result
        assert live.stats(max_age_sec=0)["unacked_count"] == 0
        assert list(archive_dir.glob("*.db"))

        # Disk reserve must prevent archival without deleting the live row.
        add_old_message(live, 2)
        free_mb = int(shutil.disk_usage(archive_dir).free // (1024 * 1024))
        cfg.overflow_archive.min_archive_free_space_mb = free_mb + 1
        guarded = OverflowArchiver(config=cfg, outbox=live).run_once()
        assert guarded["spilled"] is False, guarded
        assert guarded["reason"] == "archive_free_space_guard", guarded
        assert live.stats(max_age_sec=0)["unacked_count"] == 1
        live.close()

    print("PASS: G6.1/G6.2 live transport config is recognized and bounded")
    print("PASS: age trigger spills old rows even below 64 MiB high watermark")
    print("PASS: archive free-space reserve blocks spill before disk exhaustion")
    print("PASS: backlog replay remains disabled during live commissioning")


if __name__ == "__main__":
    main()
