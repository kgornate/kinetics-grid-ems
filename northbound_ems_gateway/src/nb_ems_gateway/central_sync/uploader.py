from __future__ import annotations

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
        )
        self.counters = UploaderCounters()
        self.started_utc = utc_now_iso()
        self.running = False
        self._stop = asyncio.Event()
        self._last_cleanup = 0.0
        self._last_status = 0.0

    async def run_forever(self) -> None:
        self.running = True
        self._stop.clear()
        log.info("central sync uploader started endpoint=%s", self.config.backend.ingest_url)
        try:
            while not self._stop.is_set():
                sent = await self.run_once()
                await self._maintenance()
                sleep_for = self.config.uploader.idle_sleep_sec if sent else self.config.uploader.scan_interval_sec
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=max(0.05, sleep_for))
                except asyncio.TimeoutError:
                    pass
        finally:
            self.running = False
            await self._write_status()
            log.info("central sync uploader stopped")

    async def stop(self) -> None:
        self._stop.set()

    async def close(self) -> None:
        try:
            await self.client.close()
        except Exception:
            pass

    async def run_once(self) -> bool:
        prepared = self.batcher.prepare()
        if not prepared:
            await self._write_status_if_due()
            return False
        await self._send_prepared(prepared)
        await self._write_status_if_due(force=True)
        return True

    async def _send_prepared(self, prepared: PreparedBatch) -> None:
        self.counters.request_count += 1
        self.counters.last_attempt_utc = utc_now_iso()
        self.counters.last_request_id = prepared.request_id
        self.counters.bytes_sent_uncompressed += len(prepared.json_bytes)
        response = await self.client.post_batch(prepared.json_bytes)
        self.counters.last_http_status = response.status_code

        # 413 is explicitly split so one oversized transport request does not
        # repeatedly block otherwise valid logical messages.
        if response.status_code == 413 and len(prepared.items) > 1:
            self.outbox.record_attempt(
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
            self.outbox.record_attempt(
                request_id=prepared.request_id,
                message_count=len(prepared.items),
                payload_bytes=len(prepared.json_bytes),
                http_status=response.status_code,
                outcome="http_success",
            )
            self._apply_partial_ack(prepared.items, response)
            return

        self.counters.request_failure_count += 1
        err = response.exception or f"HTTP {response.status_code}: {response.text[:500]}"
        self.counters.last_error = err
        self.outbox.record_attempt(
            request_id=prepared.request_id,
            message_count=len(prepared.items),
            payload_bytes=len(prepared.json_bytes),
            http_status=response.status_code,
            outcome="transport_failure",
            detail=err,
        )
        retry_after = response.retry_after_sec if response.status_code == 429 else None
        for item in prepared.items:
            self._schedule_retry(item, err, retry_after_sec=retry_after)

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

    def _apply_partial_ack(self, items: list[OutboxItem], response: TransportResponse) -> None:
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

        # Compatibility with servers returning a unified "messages" list.
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

        for item in items:
            if item.message_id in accepted:
                status, detail = accepted[item.message_id]
                normalized = "already_processed" if status == "already_processed" else "accepted"
                self.outbox.mark_accepted(item.message_id, normalized, detail)
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
                    self._schedule_retry(item, err)
                else:
                    self.counters.permanent_rejected_count += 1
                    self.outbox.mark_dead(item.message_id, error=err, detail=detail)
                continue

            # A 2xx response without an ACK for a sent logical message is not
            # treated as success. Keeping it for retry prevents silent data loss.
            self.counters.missing_ack_count += 1
            self._schedule_retry(item, "2xx response missing per-message ACK")

    def _schedule_retry(self, item: OutboxItem, error: str, retry_after_sec: float | None = None) -> None:
        if retry_after_sec is not None:
            delay = min(max(0.0, retry_after_sec), self.config.uploader.max_retry_after_sec)
        else:
            delay = self._backoff_delay(item)
        self.outbox.mark_retry(
            item.message_id,
            next_attempt_epoch=time.time() + delay,
            error=error,
            attempted_utc=utc_now_iso(),
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
            result = self.outbox.cleanup(
                acked_retention_hours=self.config.outbox.acked_retention_hours,
                dead_letter_retention_days=self.config.outbox.dead_letter_retention_days,
            )
            if result["acked_deleted"] or result["dead_deleted"]:
                log.info("central sync outbox cleanup %s", result)
        await self._write_status_if_due()

    async def _write_status_if_due(self, force: bool = False) -> None:
        now = time.time()
        if force or now - self._last_status >= self.config.uploader.status_interval_sec:
            self._last_status = now
            await self._write_status()

    async def _write_status(self) -> None:
        safe_write_json(self.config.status_file, self.status())

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
            },
            "outbox": self.outbox.stats(),
            "uploader": self.counters.__dict__.copy(),
            "status_generated_utc": utc_now_iso(),
        }


def _string_or_none(value: Any) -> str | None:
    return None if value is None else str(value)
