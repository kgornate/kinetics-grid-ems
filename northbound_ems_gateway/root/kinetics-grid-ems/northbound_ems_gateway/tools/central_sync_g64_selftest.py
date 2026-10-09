from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from nb_ems_gateway.central_sync.client import TransportResponse
from nb_ems_gateway.central_sync.config import load_central_sync_config
from nb_ems_gateway.central_sync.contracts import make_message
from nb_ems_gateway.central_sync.outbox import OutboxStore
from nb_ems_gateway.central_sync.uploader import CentralSyncUploader


def enqueue(store: OutboxStore, *, stream: str, substream: str, priority: str = "P2") -> str:
    seq = store.next_sequence(stream, substream)
    msg = make_message(
        schema_version="1.0",
        gateway_id="gw-test",
        site_id="site-test",
        stream=stream,
        substream=substream,
        sequence=seq,
        priority=priority,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        records=[{"value": seq}],
    )
    assert store.enqueue(msg)
    return msg.message_id


class MixedAckClient:
    dynamic_auth_available = True
    auth_request_count = 1
    auth_success_count = 1
    auth_failure_count = 0
    http_client_recreate_count = 0
    _consecutive_transport_failures = 0

    def __init__(self, outcomes: dict[str, str]) -> None:
        self.outcomes = outcomes

    async def post_batch(self, raw: bytes) -> TransportResponse:
        body = json.loads(raw)
        accepted = []
        rejected = []
        for message in body["messages"]:
            mid = str(message["message_id"])
            outcome = self.outcomes[mid]
            if outcome == "accepted":
                accepted.append({"message_id": mid, "status": "accepted"})
            elif outcome == "already_processed":
                accepted.append({"message_id": mid, "status": "already_processed"})
            elif outcome == "retryable_rejected":
                rejected.append({
                    "message_id": mid,
                    "status": "rejected",
                    "retryable": True,
                    "error_code": "busy",
                    "detail": "try later",
                })
            elif outcome == "missing_ack":
                pass
            else:
                raise AssertionError(outcome)
        return TransportResponse(
            status_code=200,
            body={"accepted": accepted, "rejected": rejected},
            text="",
        )

    async def close(self) -> None:
        return None


async def main() -> None:
    cfg0 = load_central_sync_config("configs/central_sync.json")
    assert cfg0.identity.software_version == "central-sync-g6.4-per-stream-ack"
    assert cfg0.uploader.worker_count == 1
    assert cfg0.uploader.fair_batching_enabled is True
    assert cfg0.backlog_replay.enabled is False

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = root / "ack.db"
        cfg = cfg0.model_copy(deep=True)
        cfg.outbox.path = str(db)
        cfg.outbox.required_mount_path = None
        cfg.outbox.fail_if_mount_missing = False
        cfg.outbox.min_free_space_mb = 0
        cfg.status_file = str(root / "status.json")
        cfg.uploader.coalescing_window_sec = 0.0

        store = OutboxStore(
            str(db),
            max_db_size_mb=64,
            min_free_space_mb=0,
            fail_if_mount_missing=False,
        )
        ids = {
            "s1": enqueue(store, stream="fast_bess_telemetry", substream="critical_pcs_bms", priority="P2"),
            "s2": enqueue(store, stream="general_asset_telemetry", substream="pcs_extended", priority="P3"),
            "s3": enqueue(store, stream="gateway_health", substream="gateway", priority="P3"),
            "s5": enqueue(store, stream="soc_controller", substream="controller", priority="P1"),
        }
        client = MixedAckClient({
            ids["s1"]: "accepted",
            ids["s2"]: "already_processed",
            ids["s3"]: "retryable_rejected",
            ids["s5"]: "missing_ack",
        })
        uploader = CentralSyncUploader(config=cfg, outbox=store, client=client)
        assert await uploader.run_once() is True
        await uploader._write_status()

        status = uploader.status()
        streams = status["stream_backend_ack"]

        s1 = streams["fast_bess_telemetry"]
        assert s1["acked_count"] == 1
        assert s1["accepted_count"] == 1
        assert s1["already_processed_count"] == 0
        assert s1["last_ack_status"] == "accepted"
        assert s1["last_ack_substream"] == "critical_pcs_bms"
        assert isinstance(s1["last_ack_sequence"], int)
        assert s1["last_ack_utc"]
        assert s1["last_backend_result"] == "accepted"

        s2 = streams["general_asset_telemetry"]
        assert s2["acked_count"] == 1
        assert s2["already_processed_count"] == 1
        assert s2["last_ack_status"] == "already_processed"

        s3 = streams["gateway_health"]
        assert s3["acked_count"] == 0
        assert s3["retryable_rejected_count"] == 1
        assert s3["last_backend_result"] == "retryable_rejected"
        assert "try later" in (s3["last_error"] or "")

        s5 = streams["soc_controller"]
        assert s5["acked_count"] == 0
        assert s5["missing_ack_count"] == 1
        assert s5["last_backend_result"] == "missing_ack"

        disk_status = json.loads(Path(cfg.status_file).read_text())
        assert disk_status["stream_backend_ack"]["fast_bess_telemetry"]["last_ack_status"] == "accepted"
        assert disk_status["stream_backend_ack"]["general_asset_telemetry"]["last_ack_status"] == "already_processed"

        store.close()
        await uploader.close()

    print("PASS: per-stream backend ACK state is derived from actual per-message backend responses")
    print("PASS: accepted and already_processed ACKs are tracked separately")
    print("PASS: retryable rejection and missing ACK are visible per stream")
    print("PASS: last ACK time/substream/sequence are exposed in status.json")
    print("PASS: G6.3 single-worker fair batching and replay-off config remain unchanged")


if __name__ == "__main__":
    asyncio.run(main())
