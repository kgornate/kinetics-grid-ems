from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path

from nb_ems_gateway.central_sync.client import TransportResponse
from nb_ems_gateway.central_sync.config import load_central_sync_config
from nb_ems_gateway.central_sync.contracts import make_message
from nb_ems_gateway.central_sync.outbox import OutboxStore
from nb_ems_gateway.central_sync.overflow_recovery import OverflowRecoveryService
from nb_ems_gateway.central_sync.uploader import CentralSyncUploader


class FakeClient:
    dynamic_auth_available = True
    auth_request_count = 0
    auth_success_count = 0
    auth_failure_count = 0
    http_client_recreate_count = 0
    _consecutive_transport_failures = 0

    def __init__(self, delay: float = 0.0) -> None:
        self.request_count = 0
        self.active = 0
        self.peak_active = 0
        self.delay = delay

    async def post_batch(self, raw: bytes) -> TransportResponse:
        self.request_count += 1
        self.active += 1
        self.peak_active = max(self.peak_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            body = json.loads(raw)
            return TransportResponse(
                status_code=200,
                body={
                    "accepted": [
                        {"message_id": m["message_id"], "status": "accepted"}
                        for m in body["messages"]
                    ]
                },
                text="",
            )
        finally:
            self.active -= 1

    async def close(self) -> None:
        return None


def add_message(store: OutboxStore, seq: int, *, stream: str = "fast_bess_telemetry") -> str:
    msg = make_message(
        schema_version="1.0",
        gateway_id="gw-test",
        site_id="site-test",
        stream=stream,
        substream="critical_pcs_bms",
        sequence=seq,
        priority="P2",
        records=[{"seq": seq, "value": seq}],
        created_at_utc="2026-10-07T00:00:00Z",
    )
    assert store.enqueue(msg)
    return msg.message_id


def new_store(path: Path) -> OutboxStore:
    return OutboxStore(
        str(path),
        max_db_size_mb=None,
        min_free_space_mb=0,
        required_mount_path=None,
        fail_if_mount_missing=False,
    )


async def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        live_db = root / "live.db"
        archive_dir = root / "archives"
        status_dir = root / "status"
        archive_dir.mkdir()
        status_dir.mkdir()
        pause_file = root / "uploader.pause"

        cfg = load_central_sync_config("configs/central_sync.json")
        cfg.outbox.path = str(live_db)
        cfg.outbox.required_mount_path = None
        cfg.outbox.fail_if_mount_missing = False
        cfg.outbox.min_free_space_mb = 0
        cfg.outbox.acked_retention_hours = 0
        cfg.uploader.pause_file = str(pause_file)
        cfg.uploader.coalescing_window_sec = 0.0
        cfg.uploader.max_messages_per_request = 25
        cfg.uploader.max_request_bytes = 128 * 1024
        cfg.uploader.worker_count = 1
        cfg.overflow_recovery.enabled = True
        cfg.overflow_recovery.archive_dir = str(archive_dir)
        cfg.overflow_recovery.status_file = str(status_dir / "recovery.json")
        cfg.overflow_recovery.uploader_status_file = str(status_dir / "recovery_uploader.json")
        cfg.overflow_recovery.live_pause_sendable_count = 25
        cfg.overflow_recovery.live_pause_oldest_age_sec = 999.0
        cfg.overflow_recovery.min_available_memory_mb = 1
        cfg.overflow_recovery.max_load1 = 999.0
        cfg.overflow_recovery.request_pause_sec = 0.01
        cfg.overflow_recovery.scan_interval_sec = 0.01
        cfg.backlog_replay.enabled = False

        live = new_store(live_db)
        add_message(live, 1)

        # 1) Pause must stop transport before rows are claimed inflight.
        pause_file.write_text('{"reason":"selftest"}\n', encoding="utf-8")
        fake = FakeClient()
        lock = asyncio.Lock()
        uploader = CentralSyncUploader(
            config=cfg,
            outbox=live,
            client=fake,
            transport_lock=lock,
        )
        sent = await uploader.run_once()
        assert sent is False
        assert fake.request_count == 0
        stats = live.stats(max_age_sec=0)
        assert stats["unacked_count"] == 1
        assert int(stats.get("inflight_count", 0)) == 0

        # 2) Resume should send the preserved live message.
        pause_file.unlink()
        sent = await uploader.run_once()
        assert sent is True
        assert fake.request_count == 1
        live.cleanup(acked_retention_hours=0, dead_letter_retention_days=30, transport_attempt_retention_days=3)

        # 3) Recovery must only select overflow files; legacy backlog is ignored.
        overflow_db = archive_dir / "central_sync_overflow_20261007T00.db"
        legacy_db = archive_dir / "central_sync_backlog_legacy.db"
        overflow = new_store(overflow_db)
        legacy = new_store(legacy_db)
        try:
            add_message(overflow, 50)
            add_message(legacy, 60)
        finally:
            overflow.close()
            legacy.close()

        recovery = OverflowRecoveryService(cfg, transport_lock=lock, client=fake)
        selected = recovery._next_archive()
        assert selected == overflow_db, selected

        # 4) Shared transport lock must serialize live/recovery HTTP requests.
        live2_db = root / "live2.db"
        archive2_db = archive_dir / "central_sync_overflow_20261007T01.db"
        live2 = new_store(live2_db)
        archive2 = new_store(archive2_db)
        add_message(live2, 2)
        add_message(archive2, 70)
        archive2.close()

        cfg2 = cfg.model_copy(deep=True)
        cfg2.outbox.path = str(live2_db)
        slow = FakeClient(delay=0.05)
        shared_lock = asyncio.Lock()
        live_uploader = CentralSyncUploader(
            config=cfg2,
            outbox=live2,
            client=slow,
            transport_lock=shared_lock,
        )
        recovery2 = OverflowRecoveryService(cfg2, transport_lock=shared_lock, client=slow)
        await asyncio.gather(
            live_uploader.run_once(),
            recovery2._replay_one(archive2_db),
        )
        assert slow.peak_active == 1, slow.peak_active
        live2.close()

        # 5) Recovery of overflow is ACK-driven and retains DB evidence.
        sent = await recovery._replay_one(overflow_db)
        assert sent is True
        assert overflow_db.exists(), "recovery must retain drained archive DB"
        marker = Path(str(overflow_db) + cfg.overflow_recovery.marker_suffix)
        assert marker.exists(), "drained archive must receive replay marker"
        marker_data = json.loads(marker.read_text())
        assert marker_data["archive_retained"] is True
        # Same unchanged DB is skipped after marker creation.
        assert recovery._next_archive() != overflow_db
        # If the hourly overflow DB is appended later, DB/WAL signature changes
        # and the retained marker must not hide the new unsent row.
        overflow_again = new_store(overflow_db)
        try:
            add_message(overflow_again, 51)
        finally:
            overflow_again.close()
        assert recovery._next_archive() == overflow_db
        await recovery._replay_one(overflow_db)
        # Legacy historical backlog is still preserved and never auto-selected.
        assert legacy_db.exists()
        assert recovery._next_archive() != legacy_db

        # 6) A paused transport also blocks automatic overflow recovery.
        pause_file.write_text('{"reason":"selftest"}\n', encoding="utf-8")
        allowed, reason, _ = recovery._resource_gate()
        assert allowed is False and reason == "transport_paused"
        pause_file.unlink()

        live.close()

        # Frozen production invariants.
        prod = load_central_sync_config("configs/central_sync.json")
        assert prod.uploader.worker_count == 1
        assert prod.backlog_replay.enabled is False
        assert prod.overflow_recovery.enabled is True
        assert prod.overflow_recovery.archive_glob == "central_sync_overflow_*.db"
        assert prod.uploader.pause_file
        assert all([
            prod.fast_bess.enabled,
            prod.general_assets.enabled,
            prod.gateway_health.enabled,
            prod.alarms_events.enabled,
            prod.soc_controller.enabled,
            prod.solis.enabled,
            prod.edge_ai.enabled,
            prod.configuration_audit.enabled,
        ])

        print("PASS: transport pause prevents HTTP upload without stopping Central Sync producers/outbox")
        print("PASS: resume uploads preserved live outbox messages")
        print("PASS: automatic recovery selects only overflow DBs and ignores legacy historical backlog")
        print("PASS: shared transport lock preserves one-request-at-a-time backend traffic")
        print("PASS: replay is backend-ACK driven and retains drained archive DB evidence")
        print("PASS: transport pause also pauses overflow replay")
        print("PASS: S1-S8 remain enabled, worker_count=1, legacy backlog replay remains OFF")


if __name__ == "__main__":
    asyncio.run(main())
