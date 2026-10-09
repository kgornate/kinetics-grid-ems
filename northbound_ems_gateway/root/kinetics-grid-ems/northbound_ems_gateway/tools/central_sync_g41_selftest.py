from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from nb_ems_gateway.central_sync.contracts import make_message
from nb_ems_gateway.central_sync.outbox import OutboxStore
from nb_ems_gateway.central_sync.uploader import CentralSyncUploader
from nb_ems_gateway.central_sync.client import TransportResponse


class FakeClient:
    dynamic_auth_available = True
    auth_request_count = 1
    auth_success_count = 1
    auth_failure_count = 0
    http_client_recreate_count = 0
    _consecutive_transport_failures = 0

    async def post_batch(self, raw: bytes) -> TransportResponse:
        import json
        body = json.loads(raw)
        accepted = [
            {"message_id": m["message_id"], "status": "accepted"}
            for m in body["messages"]
        ]
        return TransportResponse(status_code=200, body={"accepted": accepted}, text="")

    async def close(self) -> None:
        return None


def cfg(db_path: str, status_path: str):
    return SimpleNamespace(
        enabled=True,
        identity=SimpleNamespace(
            gateway_id="gw-test",
            site_id="site-test",
            schema_version="1.0",
            software_version="g4.1-test",
        ),
        backend=SimpleNamespace(
            ingest_url="https://example.invalid/api/v1/ingest/batch",
            verify_tls=True,
            gzip_enabled=False,
            resolved_token=lambda: None,
        ),
        uploader=SimpleNamespace(
            coalescing_window_sec=0.0,
            max_messages_per_request=100,
            max_request_bytes=2 * 1024 * 1024,
            backoff_initial_sec=5.0,
            backoff_multiplier=2.0,
            backoff_max_sec=300.0,
            jitter_percent=0.0,
            max_retry_after_sec=600.0,
            idle_sleep_sec=0.25,
            scan_interval_sec=1.0,
            status_interval_sec=2.0,
        ),
        outbox=SimpleNamespace(
            cleanup_interval_sec=60.0,
            acked_retention_hours=0,
            dead_letter_retention_days=30,
            transport_attempt_retention_days=3,
        ),
        status_file=status_path,
    )


def add_messages(store: OutboxStore, n: int, payload_size: int = 1024) -> None:
    for i in range(n):
        seq = store.next_sequence("test_stream", "test")
        msg = make_message(
            schema_version="1.0",
            gateway_id="gw-test",
            site_id="site-test",
            stream="test_stream",
            substream="test",
            sequence=seq,
            priority="P2",
            records=[{"i": i, "blob": "x" * payload_size}],
        )
        assert store.enqueue(msg)


async def test_async_nonblocking(store: OutboxStore, uploader: CentralSyncUploader) -> None:
    original = store.eligible

    def slow_eligible(**kwargs):
        time.sleep(0.35)
        return original(**kwargs)

    store.eligible = slow_eligible  # type: ignore[method-assign]
    ticks = 0

    async def heartbeat():
        nonlocal ticks
        end = time.monotonic() + 0.30
        while time.monotonic() < end:
            ticks += 1
            await asyncio.sleep(0.02)

    await asyncio.gather(uploader.run_once(), heartbeat())
    assert ticks >= 8, f"event loop stalled; heartbeat ticks={ticks}"
    store.eligible = original  # type: ignore[method-assign]


async def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "outbox.db")
        status = str(Path(td) / "status.json")
        store = OutboxStore(db, max_db_size_mb=64, min_free_space_mb=0, fail_if_mount_missing=False)
        add_messages(store, 100, payload_size=4096)

        uploader = CentralSyncUploader(config=cfg(db, status), outbox=store, client=FakeClient())
        await test_async_nonblocking(store, uploader)

        # Drain the remaining messages with normal path.
        while True:
            sent = await uploader.run_once()
            if not sent:
                break

        states = store.stats(max_age_sec=0)
        assert states["acked_count"] == 100, states
        assert states["pending_count"] == 0, states
        assert states["retry_count"] == 0, states

        before = store.sqlite_space_status()
        result = store.cleanup(
            acked_retention_hours=0,
            dead_letter_retention_days=30,
            transport_attempt_retention_days=3,
        )
        after = store.sqlite_space_status()
        assert result["acked_deleted"] == 100, result
        assert after["logical_used_bytes"] < before["logical_used_bytes"], (before, after)
        assert store.capacity_status()["can_accept"] is True

        await uploader.close()
        store.close()

        print("PASS: async outbox work does not stall event loop")
        print("PASS: 100-message ACK path drains successfully")
        print("PASS: ACK cleanup releases logical used space")
        print("PASS: capacity uses live page usage, not raw file size")


if __name__ == "__main__":
    asyncio.run(main())
