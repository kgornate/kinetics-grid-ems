from __future__ import annotations

# CENTRAL_SYNC_G41_RELIABILITY_V1
# CENTRAL_SYNC_G42_STATUS_THROUGHPUT_FIX_V1
# CENTRAL_SYNC_G62_CONCURRENT_LIVE_UPLOADER_V1
# CENTRAL_SYNC_G63_FAIR_SINGLE_WORKER_BATCHER_V1
# CENTRAL_SYNC_G64_PER_STREAM_ACK_OBSERVABILITY_V1
import asyncio
import hashlib
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .batcher import OutboxBatcher, PreparedBatch
from .client import CentralBackendClient, TransportResponse
from .config import CentralSyncConfig
from .outbox import OutboxItem, OutboxStore
from .status import safe_write_json, utc_now_iso

log = logging.getLogger(__name__)


@dataclass
class UploaderCounters:
    request_count: int = 0
    request_success_count: int = 0
    request_failure_count: int = 0
    accepted_count: int = 0
    already_processed_count: int = 0
    retryable_rejected_count: int = 0
    permanent_rejected_count: int = 0
    missing_ack_count: int = 0
    bytes_sent_uncompressed: int = 0
    last_attempt_utc: str | None = None
    last_success_utc: str | None = None
    last_http_status: int | None = None
    last_error: str | None = None
    last_request_id: str | None = None
    worker_count: int = 1
    active_request_count: int = 0
    peak_active_request_count: int = 0


class CentralSyncUploader:
    def __init__(
        self,
        *,
        config: CentralSyncConfig,
        outbox: OutboxStore,
        client: CentralBackendClient | Any | None = None,
    ) -> None:
        self.config = config
        self.outbox = outbox
        self.client = client or CentralBackendClient(config.backend, config.identity.gateway_id)
        self.batcher = OutboxBatcher(
            outbox,
            gateway_id=config.identity.gateway_id,
            coalescing_window_sec=config.uploader.coalescing_window_sec,
            max_messages=config.uploader.max_messages_per_request,
            max_bytes=config.uploader.max_request_bytes,
            fair_batching_enabled=bool(getattr(config.uploader, "fair_batching_enabled", False)),
            priority_bias_sec=float(getattr(config.uploader, "priority_bias_sec", 2.0)),
            candidate_scan_limit=int(getattr(config.uploader, "candidate_scan_limit", 512)),
        )
        self.counters = UploaderCounters(worker_count=int(getattr(config.uploader, "worker_count", 1)))
        self.started_utc = utc_now_iso()
        self.running = False
        self._stop = asyncio.Event()
        self._last_cleanup = 0.0
        self._last_status = 0.0
        self._stream_backend_ack: dict[str, dict[str, Any]] = {}

    async def run_forever(self) -> None:
        """Run a bounded pool of live upload workers plus one maintenance loop.

        Each worker claims its own rows through OutboxStore.eligible(). The G6
        inflight claim is atomic under the shared OutboxStore lock, so workers
        cannot send the same logical message concurrently. Backlog replay is a
        separate service/database and does not participate in this pool.
        """
        self.running = True
        self._stop.clear()
        worker_count = max(1, int(getattr(self.config.uploader, "worker_count", 1)))
        self.counters.worker_count = worker_count
        log.info(
            "central sync uploader started endpoint=%s workers=%d max_messages=%d max_bytes=%d timeout=%.1fs fair=%s bias=%.1fs candidates=%d",
            self.config.backend.ingest_url,
            worker_count,
            self.config.uploader.max_messages_per_request,
            self.config.uploader.max_request_bytes,
            self.config.backend.timeout_sec,
            bool(getattr(self.config.uploader, "fair_batching_enabled", False)),
            float(getattr(self.config.uploader, "priority_bias_sec", 2.0)),
            int(getattr(self.config.uploader, "candidate_scan_limit", 512)),
        )
        tasks = [
            asyncio.create_task(
                self._worker_loop(worker_id),
                name=f"central-sync-live-worker-{worker_id}",
            )
            for worker_id in range(1, worker_count + 1)
        ]
        tasks.append(
            asyncio.create_task(
                self._maintenance_loop(),
                name="central-sync-uploader-maintenance",
            )
        )
        try:
            await asyncio.gather(*tasks)
        finally:
            self._stop.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.running = False
            self.counters.active_request_count = 0
            await self._write_status()
            log.info("central sync uploader stopped")

    async def _worker_loop(self, worker_id: int) -> None:
        log.info("central sync live upload worker started worker=%d", worker_id)
        try:
            while not self._stop.is_set():
                sent = await self._run_transport_once()
                sleep_for = (
                    self.config.uploader.idle_sleep_sec
                    if sent
                    else self.config.uploader.scan_interval_sec
                )
                try:
                    await asyncio.wait_for(
                        self._stop.wait(),
                        timeout=max(0.05, sleep_for),
                    )
                except asyncio.TimeoutError:
                    pass
        finally:
            log.info("central sync live upload worker stopped worker=%d", worker_id)

    async def _maintenance_loop(self) -> None:
        interval = max(
            0.25,
            min(
                float(self.config.uploader.scan_interval_sec),
                float(self.config.uploader.status_interval_sec),
            ),
        )
        while not self._stop.is_set():
            await self._maintenance()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def stop(self) -> None:
        self._stop.set()

    async def close(self) -> None:
        try:
            await self.client.close()
        except Exception:
            pass

    async def run_once(self) -> bool:
        """Run exactly one transport attempt. Used by diagnostics/replay tools."""
        sent = await self._run_transport_once()
        await self._write_status_if_due()
        return sent

    async def _run_transport_once(self) -> bool:
        prepared = await asyncio.to_thread(self.batcher.prepare)
        if not prepared:
            return False
        await self._send_prepared(prepared)
        return True

    async def _send_prepared(self, prepared: PreparedBatch) -> None:
        self.counters.request_count += 1
        self.counters.last_attempt_utc = utc_now_iso()
        self.counters.last_request_id = prepared.request_id
        self.counters.bytes_sent_uncompressed += len(prepared.json_bytes)
        self.counters.active_request_count += 1
        self.counters.peak_active_request_count = max(
            self.counters.peak_active_request_count,
            self.counters.active_request_count,
        )
        try:
            response = await self.client.post_batch(prepared.json_bytes)
        finally:
            self.counters.active_request_count = max(
                0, self.counters.active_request_count - 1
            )
        self.counters.last_http_status = response.status_code

        # 413 is explicitly split so one oversized transport request does not
        # repeatedly block otherwise valid logical messages.
        if response.status_code == 413 and len(prepared.items) > 1:
            await asyncio.to_thread(
                self.outbox.record_attempt,
                request_id=prepared.request_id,
                message_count=len(prepared.items),
                payload_bytes=len(prepared.json_bytes),
                http_status=413,
                outcome="split_413",
                detail=response.text[:1000],
            )
            midpoint = len(prepared.items) // 2
            await self._send_items(prepared.items[:midpoint])
            await self._send_items(prepared.items[midpoint:])
            return

        if response.ok:
            self.counters.request_success_count += 1
            self.counters.last_success_utc = utc_now_iso()
            self.counters.last_error = None
            await asyncio.to_thread(
                self.outbox.record_attempt,
                request_id=prepared.request_id,
                message_count=len(prepared.items),
                payload_bytes=len(prepared.json_bytes),
                http_status=response.status_code,
                outcome="http_success",
            )
            await self._apply_partial_ack(prepared.items, response)
            return

        self.counters.request_failure_count += 1
        err = response.exception or f"HTTP {response.status_code}: {response.text[:500]}"
        self.counters.last_error = err
        await asyncio.to_thread(
            self.outbox.record_attempt,
            request_id=prepared.request_id,
            message_count=len(prepared.items),
            payload_bytes=len(prepared.json_bytes),
            http_status=response.status_code,
            outcome="transport_failure",
            detail=err,
        )
        retry_after = response.retry_after_sec if response.status_code == 429 else None
        attempted_utc = utc_now_iso()
        for item in prepared.items:
            self._note_stream_result(
                item,
                "transport_failure",
                when_utc=attempted_utc,
                error=err,
            )
        retry_rows = [
            self._retry_row(item, err, retry_after_sec=retry_after, attempted_utc=attempted_utc)
            for item in prepared.items
        ]
        await asyncio.to_thread(
            self.outbox.apply_batch_updates,
            retries=retry_rows,
        )

    async def _send_items(self, items: list[OutboxItem]) -> None:
        if not items:
            return
        # Rebuild a valid wrapper using the exact logical messages.
        from .contracts import TransportBatch
        import json

        batch = TransportBatch(
            gateway_id=self.config.identity.gateway_id,
            messages=[item.payload() for item in items],
        )
        body = batch.model_dump(mode="json")
        raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        prepared = PreparedBatch(request_id=batch.request_id, body=body, items=items, json_bytes=raw)
        await self._send_prepared(prepared)

    async def _apply_partial_ack(self, items: list[OutboxItem], response: TransportResponse) -> None:
        body = response.body or {}
        accepted_raw = body.get("accepted", [])
        rejected_raw = body.get("rejected", [])

        accepted: dict[str, tuple[str, str | None]] = {}
        for entry in accepted_raw if isinstance(accepted_raw, list) else []:
            if isinstance(entry, str):
                accepted[entry] = ("accepted", None)
            elif isinstance(entry, dict) and entry.get("message_id"):
                accepted[str(entry["message_id"])] = (
                    str(entry.get("status") or "accepted"),
                    _string_or_none(entry.get("detail")),
                )

        rejected: dict[str, dict[str, Any]] = {}
        for entry in rejected_raw if isinstance(rejected_raw, list) else []:
            if isinstance(entry, dict) and entry.get("message_id"):
                rejected[str(entry["message_id"])] = entry

        if not accepted and not rejected and isinstance(body.get("messages"), list):
            for entry in body["messages"]:
                if not isinstance(entry, dict) or not entry.get("message_id"):
                    continue
                mid = str(entry["message_id"])
                status = str(entry.get("status") or "")
                if status in {"accepted", "already_processed"}:
                    accepted[mid] = (status, _string_or_none(entry.get("detail")))
                elif status:
                    rejected[mid] = entry

        accepted_rows: list[tuple[str, str, str | None]] = []
        retry_rows: list[tuple[str, float, str, str | None]] = []
        dead_rows: list[tuple[str, str, str | None]] = []
        attempted_utc = utc_now_iso()

        for item in items:
            if item.message_id in accepted:
                status, detail = accepted[item.message_id]
                normalized = "already_processed" if status == "already_processed" else "accepted"
                accepted_rows.append((item.message_id, normalized, detail))
                self._note_stream_ack(item, normalized, attempted_utc)
                if normalized == "already_processed":
                    self.counters.already_processed_count += 1
                else:
                    self.counters.accepted_count += 1
                continue

            if item.message_id in rejected:
                entry = rejected[item.message_id]
                retryable = bool(entry.get("retryable", False))
                code = str(entry.get("error_code") or entry.get("code") or "rejected")
                detail = _string_or_none(entry.get("detail") or entry.get("reason"))
                err = f"{code}: {detail or 'backend rejected message'}"
                if retryable:
                    self.counters.retryable_rejected_count += 1
                    self._note_stream_result(
                        item,
                        "retryable_rejected",
                        when_utc=attempted_utc,
                        error=err,
                    )
                    retry_rows.append(
                        self._retry_row(item, err, attempted_utc=attempted_utc)
                    )
                else:
                    self.counters.permanent_rejected_count += 1
                    self._note_stream_result(
                        item,
                        "permanent_rejected",
                        when_utc=attempted_utc,
                        error=err,
                    )
                    dead_rows.append((item.message_id, err, detail))
                continue

            self.counters.missing_ack_count += 1
            self._note_stream_result(
                item,
                "missing_ack",
                when_utc=attempted_utc,
                error="2xx response missing per-message ACK",
            )
            retry_rows.append(
                self._retry_row(
                    item,
                    "2xx response missing per-message ACK",
                    attempted_utc=attempted_utc,
                )
            )

        await asyncio.to_thread(
            self.outbox.apply_batch_updates,
            accepted=accepted_rows,
            retries=retry_rows,
            dead=dead_rows,
        )

    def _stream_ack_entry(self, item: OutboxItem) -> dict[str, Any]:
        entry = self._stream_backend_ack.get(item.stream)
        if entry is None:
            entry = {
                "stream": item.stream,
                "acked_count": 0,
                "accepted_count": 0,
                "already_processed_count": 0,
                "retryable_rejected_count": 0,
                "permanent_rejected_count": 0,
                "missing_ack_count": 0,
                "transport_failure_count": 0,
                "last_ack_utc": None,
                "last_ack_status": None,
                "last_ack_substream": None,
                "last_ack_sequence": None,
                "last_backend_result_utc": None,
                "last_backend_result": None,
                "last_error": None,
            }
            self._stream_backend_ack[item.stream] = entry
        return entry

    def _note_stream_ack(self, item: OutboxItem, status: str, when_utc: str) -> None:
        entry = self._stream_ack_entry(item)
        entry["acked_count"] += 1
        if status == "already_processed":
            entry["already_processed_count"] += 1
        else:
            entry["accepted_count"] += 1
        entry["last_ack_utc"] = when_utc
        entry["last_ack_status"] = status
        entry["last_ack_substream"] = item.substream
        entry["last_ack_sequence"] = item.sequence
        entry["last_backend_result_utc"] = when_utc
        entry["last_backend_result"] = status
        entry["last_error"] = None

    def _note_stream_result(
        self,
        item: OutboxItem,
        result: str,
        *,
        when_utc: str,
        error: str | None = None,
    ) -> None:
        entry = self._stream_ack_entry(item)
        if result == "retryable_rejected":
            entry["retryable_rejected_count"] += 1
        elif result == "permanent_rejected":
            entry["permanent_rejected_count"] += 1
        elif result == "missing_ack":
            entry["missing_ack_count"] += 1
        elif result == "transport_failure":
            entry["transport_failure_count"] += 1
        entry["last_backend_result_utc"] = when_utc
        entry["last_backend_result"] = result
        entry["last_error"] = error

    def _retry_row(
        self,
        item: OutboxItem,
        error: str,
        retry_after_sec: float | None = None,
        attempted_utc: str | None = None,
    ) -> tuple[str, float, str, str | None]:
        if retry_after_sec is not None:
            delay = min(max(0.0, retry_after_sec), self.config.uploader.max_retry_after_sec)
        else:
            delay = self._backoff_delay(item)
        return (
            item.message_id,
            time.time() + delay,
            error,
            attempted_utc or utc_now_iso(),
        )

    def _schedule_retry(self, item: OutboxItem, error: str, retry_after_sec: float | None = None) -> None:
        # Kept for compatibility with any external tests/tools. Runtime batch
        # paths use apply_batch_updates() to avoid one COMMIT per message.
        message_id, next_epoch, err, attempted_utc = self._retry_row(
            item, error, retry_after_sec=retry_after_sec
        )
        self.outbox.mark_retry(
            message_id,
            next_attempt_epoch=next_epoch,
            error=err,
            attempted_utc=attempted_utc,
        )

    def _backoff_delay(self, item: OutboxItem) -> float:
        attempt_number = item.attempt_count + 1
        base = self.config.uploader.backoff_initial_sec * (
            self.config.uploader.backoff_multiplier ** max(0, attempt_number - 1)
        )
        base = min(base, self.config.uploader.backoff_max_sec)
        pct = max(0.0, min(self.config.uploader.jitter_percent, 0.95))
        if pct <= 0:
            return base
        seed = f"{self.config.identity.gateway_id}|{item.message_id}|{attempt_number}".encode("utf-8")
        digest = hashlib.sha256(seed).digest()
        unit = int.from_bytes(digest[:8], "big") / float(2**64 - 1)
        factor = (1.0 - pct) + (2.0 * pct * unit)
        return max(0.05, min(base * factor, self.config.uploader.backoff_max_sec))

    async def _maintenance(self) -> None:
        now = time.time()
        if now - self._last_cleanup >= self.config.outbox.cleanup_interval_sec:
            self._last_cleanup = now
            result = await asyncio.to_thread(
                self.outbox.cleanup,
                acked_retention_hours=self.config.outbox.acked_retention_hours,
                dead_letter_retention_days=self.config.outbox.dead_letter_retention_days,
                transport_attempt_retention_days=(
                    self.config.outbox.transport_attempt_retention_days
                ),
            )
            if any(result.values()):
                log.info("central sync outbox cleanup %s", result)
        await self._write_status_if_due()

    async def _write_status_if_due(self, force: bool = False) -> None:
        now = time.time()
        if force or now - self._last_status >= self.config.uploader.status_interval_sec:
            self._last_status = now
            await self._write_status()

    async def _write_status(self) -> None:
        await asyncio.to_thread(
            lambda: safe_write_json(self.config.status_file, self.status())
        )

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "running": self.running,
            "started_utc": self.started_utc,
            "identity": {
                "site_id": self.config.identity.site_id,
                "gateway_id": self.config.identity.gateway_id,
                "schema_version": self.config.identity.schema_version,
                "software_version": self.config.identity.software_version,
            },
            "backend": {
                "ingest_url": self.config.backend.ingest_url,
                "verify_tls": self.config.backend.verify_tls,
                "gzip_enabled": self.config.backend.gzip_enabled,
                "token_configured": bool(self.config.backend.resolved_token()),
                "dynamic_auth_available": bool(getattr(self.client, "dynamic_auth_available", False)),
                "auth_request_count": int(getattr(self.client, "auth_request_count", 0)),
                "auth_success_count": int(getattr(self.client, "auth_success_count", 0)),
                "auth_failure_count": int(getattr(self.client, "auth_failure_count", 0)),
                "http_client_recreate_count": int(getattr(self.client, "http_client_recreate_count", 0)),
                "consecutive_transport_failures": int(getattr(self.client, "_consecutive_transport_failures", 0)),
            },
            "outbox": self.outbox.stats(max_age_sec=30.0),
            "uploader": self.counters.__dict__.copy(),
            "stream_backend_ack": {
                stream: dict(values)
                for stream, values in sorted(self._stream_backend_ack.items())
            },
            "status_generated_utc": utc_now_iso(),
        }


def _string_or_none(value: Any) -> str | None:
    return None if value is None else str(value)
