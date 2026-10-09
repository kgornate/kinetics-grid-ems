from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .contracts import make_message, utc_now_iso
from .outbox import OutboxCapacityError, OutboxStore
from .status import safe_write_json

log = logging.getLogger(__name__)


def fingerprint(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_iso_epoch_ms(value: Any) -> int | None:
    if not value:
        return None
    try:
        from datetime import datetime
        text = str(value).replace("Z", "+00:00")
        return int(datetime.fromisoformat(text).timestamp() * 1000)
    except Exception:
        return None


def quality_from_point(point: Any) -> str:
    if isinstance(point, dict):
        return str(point.get("quality") or "unknown")
    return "unknown"


def emit_message(
    *,
    config: Any,
    outbox: OutboxStore,
    stream: str,
    substream: str | None,
    priority: str,
    records: list[dict[str, Any]],
    created_at_utc: str | None = None,
) -> tuple[bool, Any]:
    if not records:
        return False, None
    sequence = outbox.next_sequence(stream, substream)
    message = make_message(
        schema_version=config.identity.schema_version,
        gateway_id=config.identity.gateway_id,
        site_id=config.identity.site_id,
        organization_id=config.identity.organization_id,
        gateway_software_version=config.identity.software_version,
        stream=stream,
        substream=substream,
        sequence=sequence,
        priority=priority,
        records=records,
        compression="gzip" if config.backend.gzip_enabled else "none",
        created_at_utc=created_at_utc,
    )
    inserted = outbox.enqueue(message)
    return inserted, message


@dataclass
class ProducerCounters:
    poll_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    message_count: int = 0
    record_count: int = 0
    last_poll_utc: str | None = None
    last_success_utc: str | None = None
    last_enqueue_utc: str | None = None
    last_error: str | None = None
    last_message_id: str | None = None
    last_sequence: int | None = None


class ProducerLoopMixin:
    producer_config: Any
    counters: ProducerCounters
    running: bool
    _stop: asyncio.Event

    async def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        if not self.producer_config.enabled:
            return
        self.running = True
        self._stop.clear()
        interval = max(0.1, float(self.producer_config.poll_interval_sec))
        try:
            while not self._stop.is_set():
                try:
                    await self.collect_once()
                except Exception as exc:  # producer failure must not kill Central Sync
                    self.counters.failure_count += 1
                    self.counters.last_error = f"{type(exc).__name__}: {exc}"
                    self._write_status()
                    log.exception("Central Sync producer failed")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
        finally:
            self.running = False
            self._write_status()

    def _write_status(self) -> None:
        payload = {
            "running": bool(self.running),
            "started_utc": getattr(self, "started_utc", None),
            **self.counters.__dict__,
        }
        try:
            safe_write_json(self.producer_config.status_file, payload)
        except Exception:
            pass

    def status(self) -> dict[str, Any]:
        return {"running": bool(self.running), "started_utc": getattr(self, "started_utc", None), **self.counters.__dict__}
