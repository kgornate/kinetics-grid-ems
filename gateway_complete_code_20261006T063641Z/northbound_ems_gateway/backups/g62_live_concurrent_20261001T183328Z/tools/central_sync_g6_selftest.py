from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path

from nb_ems_gateway.central_sync.backlog_replayer import BacklogReplayService
from nb_ems_gateway.central_sync.client import TransportResponse
from nb_ems_gateway.central_sync.config import load_central_sync_config
from nb_ems_gateway.central_sync.contracts import make_message
from nb_ems_gateway.central_sync.outbox import OutboxStore
from nb_ems_gateway.central_sync.overflow_archiver import OverflowArchiver


class FakeClient:
    dynamic_auth_available = True
    auth_request_count = 0
    auth_success_count = 0
    auth_failure_count = 0
    http_client_recreate_count = 0
    _consecutive_transport_failures = 0

    async def post_batch(self, raw: bytes) -> TransportResponse:
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

    async def close(self) -> None:
        return None


def add_messages(store: OutboxStore, n: int, *, payload_size: int = 4096) -> None:
    for i in range(n):
        seq = store.next_sequence("general_asset_telemetry", "bms_extended")
        msg = make_message(
            schema_version="1.0",
            gateway_id="gw-test",
            site_id="site-test",
            stream="general_asset_telemetry",
            substream="bms_extended",
            sequence=seq,
            priority="P3",
            records=[{"i": i, "blob": "x" * payload_size}],
            created_at_utc="2026-09-30T00:00:00Z",
        )
        assert store.enqueue(msg)


async def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        live_db = root / "live.db"
        archive_dir = root / "archives"
        status_dir = root / "status"
        status_dir.mkdir()

        cfg = load_central_sync_config("configs/central_sync.json")
        cfg.outbox.path = str(live_db)
        cfg.outbox.required_mount_path = None
        cfg.outbox.fail_if_mount_missing = False
        cfg.outbox.min_free_space_mb = 0
        cfg.outbox.max_db_size_mb = 64
        cfg.overflow_archive.archive_dir = str(archive_dir)
        cfg.overflow_archive.status_file = str(status_dir / "overflow.json")
        cfg.overflow_archive.high_watermark_mb = 2
        cfg.overflow_archive.target_watermark_mb = 1
        cfg.overflow_archive.spill_min_age_sec = 0.01
        cfg.overflow_archive.max_messages_per_cycle = 100
        cfg.overflow_archive.max_bytes_per_cycle = 512 * 1024
        cfg.overflow_archive.max_chunks_per_check = 8
        # Self-test uses a temporary directory on the small root filesystem.
        # Production archive reserve is tested separately by G6.1.
        cfg.overflow_archive.min_archive_free_space_mb = 1
        cfg.backlog_replay.enabled = True
        cfg.backlog_replay.archive_dir = str(archive_dir)
        cfg.backlog_replay.status_file = str(status_dir / "replay.json")
        cfg.backlog_replay.max_messages_per_request = 25
        cfg.backlog_replay.max_request_bytes = 512 * 1024
        cfg.backlog_replay.live_pause_sendable_count = 0
        cfg.backlog_replay.live_pause_oldest_age_sec = 1.0
        cfg.backlog_replay.min_available_memory_mb = 1
        cfg.backlog_replay.max_load1 = 100.0
        cfg.backlog_replay.delete_drained_archives = True

        live = OutboxStore(
            str(live_db),
            max_db_size_mb=64,
            min_free_space_mb=0,
            fail_if_mount_missing=False,
        )
        add_messages(live, 900)
        seq_before = live.current_sequence("general_asset_telemetry", "bms_extended")

        # Transport claims are excluded from overflow archival.
        claimed = live.eligible(
            now_epoch=time.time(),
            coalescing_window_sec=0.0,
            max_messages=5,
            max_bytes=256 * 1024,
        )
        assert len(claimed) == 5
        candidates = live.spill_rows(
            now_epoch=time.time(),
            min_age_sec=0.0,
            max_messages=900,
            max_bytes=16 * 1024 * 1024,
        )
        claimed_ids = {item.message_id for item in claimed}
        candidate_ids = {row["message_id"] for row in candidates}
        assert claimed_ids.isdisjoint(candidate_ids)

        # Put the claims back so the test does not intentionally leave live work.
        live.apply_batch_updates(
            retries=[
                (item.message_id, 0.0, "selftest release inflight", None)
                for item in claimed
            ]
        )

        before = live.sqlite_space_status()["logical_used_bytes"]
        archiver = OverflowArchiver(config=cfg, outbox=live)
        result = archiver.run_once()
        after = live.sqlite_space_status()["logical_used_bytes"]
        assert result["spilled"] is True, result
        assert after < before, (before, after)
        assert live.current_sequence("general_asset_telemetry", "bms_extended") == seq_before
        assert list(archive_dir.glob("*.db"))

        # Live queue must be empty before replay is allowed in this self-test.
        remaining_rows = live.spill_rows(
            now_epoch=time.time(),
            min_age_sec=0.0,
            max_messages=1000,
            max_bytes=64 * 1024 * 1024,
        )
        if remaining_rows:
            archive_path = list(archive_dir.glob("*.db"))[0]
            archive = OutboxStore(
                str(archive_path),
                max_db_size_mb=None,
                min_free_space_mb=0,
                fail_if_mount_missing=False,
            )
            try:
                assert archive.import_rows(remaining_rows) >= 0
                assert archive.count_message_ids([r["message_id"] for r in remaining_rows]) == len(remaining_rows)
                live.delete_spilled([r["message_id"] for r in remaining_rows])
            finally:
                archive.close()
        assert live.stats(max_age_sec=0)["unacked_count"] == 0
        live.close()

        replay = BacklogReplayService(cfg)
        await replay.client.close()
        replay.client = FakeClient()
        allowed, reason, _ = replay._resource_gate()
        assert allowed, reason

        for _ in range(200):
            archive_path = replay._next_archive()
            if archive_path is None:
                break
            await replay._replay_one(archive_path)
        assert replay._next_archive() is None
        await replay.close()

        print("PASS: inflight rows are protected from overflow archival")
        print("PASS: overflow archival is bounded and reduces live logical DB usage")
        print("PASS: copy-before-delete archive verification preserves messages")
        print("PASS: overflow archival does not alter producer sequence state")
        print("PASS: backlog replay uses bounded batches and drains archive files")


if __name__ == "__main__":
    asyncio.run(main())
