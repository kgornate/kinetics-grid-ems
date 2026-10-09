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
from nb_ems_gateway.central_sync.uploader import CentralSyncUploader


class ConcurrentFakeClient:
    dynamic_auth_available = True
    auth_request_count = 1
    auth_success_count = 1
    auth_failure_count = 0
    http_client_recreate_count = 0
    _consecutive_transport_failures = 0

    def __init__(self, delay_sec: float = 0.10) -> None:
        self.delay_sec = delay_sec
        self.call_count = 0
        self.active = 0
        self.peak_active = 0
        self.seen_ids: set[str] = set()
        self.duplicate_ids: set[str] = set()

    async def post_batch(self, raw: bytes) -> TransportResponse:
        body = json.loads(raw)
        ids = [str(m["message_id"]) for m in body["messages"]]
        self.call_count += 1
        self.active += 1
        self.peak_active = max(self.peak_active, self.active)
        try:
            for mid in ids:
                if mid in self.seen_ids:
                    self.duplicate_ids.add(mid)
                self.seen_ids.add(mid)
            await asyncio.sleep(self.delay_sec)
            return TransportResponse(
                status_code=200,
                body={
                    "accepted": [
                        {"message_id": mid, "status": "accepted"}
                        for mid in ids
                    ]
                },
                text="",
            )
        finally:
            self.active -= 1

    async def close(self) -> None:
        return None


def add_messages(store: OutboxStore, n: int) -> None:
    for i in range(n):
        seq = store.next_sequence("fast_bess_telemetry", "critical_pcs_bms")
        msg = make_message(
            schema_version="1.0",
            gateway_id="gw-test",
            site_id="site-test",
            stream="fast_bess_telemetry",
            substream="critical_pcs_bms",
            sequence=seq,
            priority="P1",
            records=[{"i": i, "blob": "x" * 2048}],
        )
        assert store.enqueue(msg)


async def wait_until(predicate, *, timeout_sec: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("timeout waiting for concurrent uploader self-test condition")


async def main() -> None:
    cfg0 = load_central_sync_config("configs/central_sync.json")
    assert cfg0.identity.software_version in {
        "central-sync-g6.2-live-concurrent",
        "central-sync-g6.3-fair-single-worker",
        "central-sync-g6.4-per-stream-ack",
    }
    if cfg0.identity.software_version == "central-sync-g6.2-live-concurrent":
        assert cfg0.uploader.worker_count == 4
    else:
        assert cfg0.uploader.worker_count == 1
        assert cfg0.uploader.fair_batching_enabled is True
    assert cfg0.uploader.max_messages_per_request == 25
    assert cfg0.uploader.max_request_bytes == 128 * 1024
    assert cfg0.backend.timeout_sec == 30.0
    assert cfg0.backlog_replay.enabled is False

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = root / "live.db"
        cfg = cfg0.model_copy(deep=True)
        cfg.outbox.path = str(db)
        cfg.outbox.required_mount_path = None
        cfg.outbox.fail_if_mount_missing = False
        cfg.outbox.min_free_space_mb = 0
        cfg.outbox.max_db_size_mb = 64
        cfg.outbox.cleanup_interval_sec = 3600.0
        cfg.status_file = str(root / "status.json")
        cfg.uploader.worker_count = 4
        cfg.uploader.max_messages_per_request = 5
        cfg.uploader.max_request_bytes = 64 * 1024
        cfg.uploader.coalescing_window_sec = 0.0
        cfg.uploader.idle_sleep_sec = 0.01
        cfg.uploader.scan_interval_sec = 0.02
        cfg.uploader.status_interval_sec = 0.05

        store = OutboxStore(
            str(db),
            max_db_size_mb=64,
            min_free_space_mb=0,
            fail_if_mount_missing=False,
        )
        add_messages(store, 40)
        fake = ConcurrentFakeClient(delay_sec=0.10)
        uploader = CentralSyncUploader(config=cfg, outbox=store, client=fake)

        task = asyncio.create_task(uploader.run_forever())
        await wait_until(
            lambda: store.stats(max_age_sec=0)["unacked_count"] == 0,
            timeout_sec=8.0,
        )
        await uploader.stop()
        await asyncio.wait_for(task, timeout=3.0)

        stats = store.stats(max_age_sec=0)
        assert stats["unacked_count"] == 0, stats
        assert fake.call_count >= 8, fake.call_count
        assert fake.peak_active == 4, fake.peak_active
        assert uploader.counters.peak_active_request_count == 4, uploader.counters
        assert uploader.counters.worker_count == 4
        assert not fake.duplicate_ids, fake.duplicate_ids
        assert len(fake.seen_ids) == 40, len(fake.seen_ids)
        assert uploader.counters.request_failure_count == 0
        assert uploader.counters.accepted_count == 40
        store.close()
        await uploader.close()

    # worker_count only applies to run_forever; run_once must remain exactly one
    # attempt so backlog replay and diagnostic callers retain old semantics.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = root / "once.db"
        cfg = cfg0.model_copy(deep=True)
        cfg.outbox.path = str(db)
        cfg.outbox.required_mount_path = None
        cfg.outbox.fail_if_mount_missing = False
        cfg.outbox.min_free_space_mb = 0
        cfg.status_file = str(root / "status.json")
        cfg.uploader.max_messages_per_request = 5
        cfg.uploader.max_request_bytes = 64 * 1024
        cfg.uploader.coalescing_window_sec = 0.0

        store = OutboxStore(
            str(db),
            max_db_size_mb=64,
            min_free_space_mb=0,
            fail_if_mount_missing=False,
        )
        add_messages(store, 10)
        fake = ConcurrentFakeClient(delay_sec=0.01)
        uploader = CentralSyncUploader(config=cfg, outbox=store, client=fake)
        sent = await uploader.run_once()
        assert sent is True
        assert fake.call_count == 1, fake.call_count
        assert store.stats(max_age_sec=0)["unacked_count"] == 5
        store.close()
        await uploader.close()

    print("PASS: uploader concurrency capability remains regression-tested")
    print("PASS: four workers issue four overlapping HTTP requests")
    print("PASS: inflight claims prevent duplicate message delivery across workers")
    print("PASS: all 40 live messages ACK exactly once in concurrent test")
    print("PASS: run_once remains single-request for diagnostics/backlog replay")
    print("PASS: backlog replay remains disabled during live commissioning")


if __name__ == "__main__":
    asyncio.run(main())
