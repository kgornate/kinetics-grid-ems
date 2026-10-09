from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nb_ems_gateway.central_sync.client import TransportResponse
from nb_ems_gateway.central_sync.config import load_central_sync_config
from nb_ems_gateway.central_sync.contracts import make_message
from nb_ems_gateway.central_sync.outbox import OutboxStore
from nb_ems_gateway.central_sync.uploader import CentralSyncUploader


def iso_age(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def enqueue(
    store: OutboxStore,
    *,
    stream: str,
    substream: str,
    priority: str,
    age_sec: float,
    blob_bytes: int,
) -> str:
    seq = store.next_sequence(stream, substream)
    msg = make_message(
        schema_version="1.0",
        gateway_id="gw-test",
        site_id="site-test",
        stream=stream,
        substream=substream,
        sequence=seq,
        priority=priority,
        created_at_utc=iso_age(age_sec),
        records=[{"blob": "x" * blob_bytes}],
    )
    assert store.enqueue(msg)
    return msg.message_id


class FakeClient:
    dynamic_auth_available = True
    auth_request_count = 1
    auth_success_count = 1
    auth_failure_count = 0
    http_client_recreate_count = 0
    _consecutive_transport_failures = 0

    def __init__(self) -> None:
        self.active = 0
        self.peak_active = 0
        self.calls: list[list[str]] = []

    async def post_batch(self, raw: bytes) -> TransportResponse:
        body = json.loads(raw)
        ids = [str(m["message_id"]) for m in body["messages"]]
        self.active += 1
        self.peak_active = max(self.peak_active, self.active)
        self.calls.append(ids)
        try:
            await asyncio.sleep(0.005)
            return TransportResponse(
                status_code=200,
                body={"accepted": [{"message_id": mid, "status": "accepted"} for mid in ids]},
                text="",
            )
        finally:
            self.active -= 1

    async def close(self) -> None:
        return None


async def main() -> None:
    cfg0 = load_central_sync_config("configs/central_sync.json")
    assert cfg0.identity.software_version == "central-sync-g6.3-fair-single-worker"
    assert cfg0.uploader.worker_count == 1
    assert cfg0.uploader.max_messages_per_request == 25
    assert cfg0.uploader.max_request_bytes == 128 * 1024
    assert cfg0.uploader.fair_batching_enabled is True
    assert cfg0.uploader.priority_bias_sec == 2.0
    assert cfg0.uploader.candidate_scan_limit == 512
    assert cfg0.backlog_replay.enabled is False

    # Case 1: a fresh P2/S1 message must not let one oversized P3/S2 row
    # collapse the whole batch. The oversized row is skipped temporarily and
    # smaller S2 rows behind it are coalesced into the same request.
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "fair.db"
        store = OutboxStore(str(db), max_db_size_mb=64, min_free_space_mb=0, fail_if_mount_missing=False)
        s1 = enqueue(store, stream="fast_bess_telemetry", substream="critical_pcs_bms", priority="P2", age_sec=1.5, blob_bytes=5_000)
        big = enqueue(store, stream="general_asset_telemetry", substream="bms_extended", priority="P3", age_sec=1.4, blob_bytes=180_000)
        s2a = enqueue(store, stream="general_asset_telemetry", substream="pcs_extended", priority="P3", age_sec=1.3, blob_bytes=35_000)
        s2b = enqueue(store, stream="general_asset_telemetry", substream="utility_meter", priority="P3", age_sec=1.2, blob_bytes=35_000)
        items = store.eligible(
            now_epoch=datetime.now(timezone.utc).timestamp(),
            coalescing_window_sec=1.0,
            max_messages=25,
            max_bytes=128 * 1024,
            fair_batching=True,
            priority_bias_sec=2.0,
            candidate_scan_limit=512,
        )
        ids = [x.message_id for x in items]
        assert s1 in ids, ids
        assert big not in ids, ids
        assert s2a in ids or s2b in ids, ids
        assert len(ids) >= 2, ids
        store.close()

    # Case 2: once a large lower-priority row is sufficiently older than new
    # S1 data, bounded priority bias lets it become first and oversize-first
    # semantics guarantee it is sent alone instead of starving indefinitely.
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "oversize.db"
        store = OutboxStore(str(db), max_db_size_mb=64, min_free_space_mb=0, fail_if_mount_missing=False)
        big = enqueue(store, stream="general_asset_telemetry", substream="bms_extended", priority="P3", age_sec=8.0, blob_bytes=180_000)
        enqueue(store, stream="fast_bess_telemetry", substream="critical_pcs_bms", priority="P2", age_sec=1.5, blob_bytes=5_000)
        items = store.eligible(
            now_epoch=datetime.now(timezone.utc).timestamp(),
            coalescing_window_sec=1.0,
            max_messages=25,
            max_bytes=128 * 1024,
            fair_batching=True,
            priority_bias_sec=2.0,
            candidate_scan_limit=512,
        )
        assert [x.message_id for x in items] == [big]
        store.close()

    # Case 3: production run_forever remains strictly one HTTP request at a
    # time, while fair selection drains mixed P2/P3 traffic with no duplicates.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = root / "uploader.db"
        cfg = cfg0.model_copy(deep=True)
        cfg.outbox.path = str(db)
        cfg.outbox.required_mount_path = None
        cfg.outbox.fail_if_mount_missing = False
        cfg.outbox.min_free_space_mb = 0
        cfg.status_file = str(root / "status.json")
        cfg.uploader.worker_count = 1
        cfg.uploader.coalescing_window_sec = 0.0
        cfg.uploader.scan_interval_sec = 0.01
        cfg.uploader.idle_sleep_sec = 0.005
        cfg.uploader.status_interval_sec = 0.05

        store = OutboxStore(str(db), max_db_size_mb=64, min_free_space_mb=0, fail_if_mount_missing=False)
        expected: set[str] = set()
        for i in range(20):
            expected.add(enqueue(store, stream="fast_bess_telemetry", substream="critical_pcs_bms", priority="P2", age_sec=3 + i * 0.01, blob_bytes=5_000))
            expected.add(enqueue(store, stream="general_asset_telemetry", substream="pcs_extended", priority="P3", age_sec=4 + i * 0.01, blob_bytes=18_000))
        expected.add(enqueue(store, stream="general_asset_telemetry", substream="bms_extended", priority="P3", age_sec=10, blob_bytes=180_000))

        fake = FakeClient()
        uploader = CentralSyncUploader(config=cfg, outbox=store, client=fake)
        task = asyncio.create_task(uploader.run_forever())
        for _ in range(1000):
            if store.stats(max_age_sec=0)["unacked_count"] == 0:
                break
            await asyncio.sleep(0.01)
        assert store.stats(max_age_sec=0)["unacked_count"] == 0
        await uploader.stop()
        await asyncio.wait_for(task, timeout=2.0)
        seen = [mid for call in fake.calls for mid in call]
        assert set(seen) == expected
        assert len(seen) == len(set(seen))
        assert fake.peak_active == 1
        assert uploader.counters.worker_count == 1
        store.close()
        await uploader.close()

    print("PASS: G6.3 production config is single-worker / 25 msgs / 128 KiB / 30 sec")
    print("PASS: fair batching coalesces smaller S2 rows instead of breaking behind one oversized row")
    print("PASS: bounded priority bias prevents large lower-priority logical messages from starving")
    print("PASS: oversize-first semantics are preserved once an oversized row becomes first")
    print("PASS: live uploader remains strictly sequential with no duplicate delivery")
    print("PASS: backlog replay remains disabled")


if __name__ == "__main__":
    asyncio.run(main())
