from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from .config import CentralSyncConfig
from .contracts import make_message, utc_now_iso
from .fast_bess_live_source import FastBESSLiveSource
from .outbox import OutboxStore
from .status import safe_write_json

log = logging.getLogger(__name__)


@dataclass
class FastBESSProducerCounters:
    poll_count: int = 0
    poll_success_count: int = 0
    poll_failure_count: int = 0
    duplicate_snapshot_count: int = 0
    shape_rejection_count: int = 0
    enqueue_count: int = 0
    enqueue_failure_count: int = 0
    record_count: int = 0
    gap_count: int = 0
    last_poll_utc: str | None = None
    last_success_utc: str | None = None
    last_enqueue_utc: str | None = None
    last_error: str | None = None
    last_message_id: str | None = None
    last_sequence: int | None = None
    last_sampled_at_utc: str | None = None
    last_sampled_at_epoch_ms: int | None = None
    last_snapshot_age_sec: float | None = None
    last_gap_ms: int | None = None


class FastBESSProducer:
    """Produce S1 Fast BESS telemetry from the volatile live-cache snapshot.

    Primary source path:
      NorthBound AssetManager cache -> FastBESSLogger thread -> /run RAM JSON
      -> this producer -> G1 durable Central Sync outbox.

    This producer never reads the NorthBound historian SQLite DB and never polls
    Modbus. The Central Sync outbox remains intentionally durable for delivery.
    """

    def __init__(
        self,
        *,
        config: CentralSyncConfig,
        outbox: OutboxStore,
        source: FastBESSLiveSource | Any | None = None,
    ) -> None:
        self.config = config
        self.producer_config = config.fast_bess
        self.outbox = outbox
        self.source = source or FastBESSLiveSource(
            self.producer_config.live_snapshot_path,
            max_snapshot_age_sec=self.producer_config.max_snapshot_age_sec,
        )
        self.counters = FastBESSProducerCounters()
        self.running = False
        self.started_utc = utc_now_iso()
        self._stop = asyncio.Event()
        self._last_sampled_epoch_ms: int | None = None

    async def close(self) -> None:
        return None

    async def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        if not self.producer_config.enabled:
            log.info("Fast BESS producer disabled")
            return

        interval = max(0.1, float(self.producer_config.sample_interval_sec))
        self.running = True
        self._stop.clear()
        log.info(
            "Fast BESS producer started interval=%.3fs source=%s stream=%s/%s",
            interval,
            self.producer_config.live_snapshot_path,
            self.producer_config.stream,
            self.producer_config.substream,
        )

        next_tick = time.monotonic()
        try:
            while not self._stop.is_set():
                delay = max(0.0, next_tick - time.monotonic())
                if delay:
                    try:
                        await asyncio.wait_for(self._stop.wait(), timeout=delay)
                        break
                    except asyncio.TimeoutError:
                        pass
                await self.collect_once()
                next_tick += interval
                if next_tick < time.monotonic() - interval:
                    next_tick = time.monotonic() + interval
        finally:
            self.running = False
            self._write_status()
            log.info("Fast BESS producer stopped")

    async def collect_once(self) -> dict[str, Any]:
        now_utc = utc_now_iso()
        self.counters.poll_count += 1
        self.counters.last_poll_utc = now_utc

        try:
            snapshot = await asyncio.to_thread(self.source.read)
            self._validate_snapshot(snapshot)
        except Exception as exc:
            error = _exc_text(exc)
            self.counters.poll_failure_count += 1
            self.counters.last_error = error
            if "shape" in error.lower() or "expected" in error.lower():
                self.counters.shape_rejection_count += 1
            self._write_status()
            log.warning("Fast BESS live snapshot rejected: %s", error)
            return {
                "emitted": False,
                "reason": "source_error",
                "error": error,
                "outbox": self.outbox.stats(),
            }

        sampled_ms = int(snapshot["sampled_at_epoch_ms"])
        sampled_utc = str(snapshot.get("sampled_at_utc") or "")
        self.counters.poll_success_count += 1
        self.counters.last_success_utc = now_utc
        self.counters.last_snapshot_age_sec = _float_or_none(snapshot.get("snapshot_age_sec"))
        self.counters.last_error = None

        if self._last_sampled_epoch_ms == sampled_ms:
            self.counters.duplicate_snapshot_count += 1
            self._write_status()
            return {
                "emitted": False,
                "reason": "duplicate_snapshot",
                "sampled_at_epoch_ms": sampled_ms,
                "outbox": self.outbox.stats(),
            }

        if self._last_sampled_epoch_ms is not None:
            gap_ms = sampled_ms - self._last_sampled_epoch_ms
            self.counters.last_gap_ms = gap_ms
            if gap_ms > int(self.producer_config.sample_interval_sec * 2500):
                self.counters.gap_count += 1
                log.warning("Fast BESS sample gap detected: %d ms", gap_ms)

        records: list[dict[str, Any]] = []
        for raw in snapshot.get("records") or []:
            record = dict(raw)
            record["record_type"] = "fast_bess_sample"
            record["sample_source"] = "asset_manager_live_cache"
            record["persisted_source"] = False
            record["snapshot_age_sec"] = snapshot.get("snapshot_age_sec")
            records.append(record)

        sequence = self.outbox.next_sequence(
            self.producer_config.stream,
            self.producer_config.substream,
        )
        message = make_message(
            schema_version=self.config.identity.schema_version,
            gateway_id=self.config.identity.gateway_id,
            site_id=self.config.identity.site_id,
            stream=self.producer_config.stream,
            substream=self.producer_config.substream,
            sequence=sequence,
            priority=self.producer_config.priority,
            records=records,
            created_at_utc=sampled_utc or now_utc,
        )

        try:
            inserted = self.outbox.enqueue(message)
        except Exception as exc:
            self.counters.enqueue_failure_count += 1
            self.counters.last_error = f"outbox enqueue failed: {_exc_text(exc)}"
            self._write_status()
            raise

        if not inserted:
            self._write_status()
            return {
                "emitted": False,
                "reason": "outbox_duplicate",
                "sequence": sequence,
                "message_id": message.message_id,
                "outbox": self.outbox.stats(),
            }

        self._last_sampled_epoch_ms = sampled_ms
        self.counters.enqueue_count += 1
        self.counters.record_count += len(records)
        self.counters.last_enqueue_utc = now_utc
        self.counters.last_message_id = message.message_id
        self.counters.last_sequence = sequence
        self.counters.last_sampled_at_utc = sampled_utc
        self.counters.last_sampled_at_epoch_ms = sampled_ms
        self._write_status()

        return {
            "emitted": True,
            "message_id": message.message_id,
            "sequence": sequence,
            "record_count": len(records),
            "sampled_at_utc": sampled_utc,
            "sampled_at_epoch_ms": sampled_ms,
            "snapshot_age_sec": snapshot.get("snapshot_age_sec"),
            "sources": [r.get("source_id") for r in records],
            "outbox": self.outbox.stats(),
        }

    def _validate_snapshot(self, snapshot: dict[str, Any]) -> None:
        cfg = self.producer_config
        records = snapshot.get("records")
        if not isinstance(records, list):
            raise ValueError("Fast BESS shape error: records must be a list")
        if snapshot.get("sample_source") != "asset_manager_live_cache":
            raise ValueError("Fast BESS shape error: source is not live AssetManager cache")
        if snapshot.get("persisted_source") is not False:
            raise ValueError("Fast BESS shape error: persisted_source must be false")
        if not cfg.strict_shape:
            return

        if len(records) != cfg.expected_bess_count:
            raise ValueError(
                f"Fast BESS expected {cfg.expected_bess_count} BESS records, got {len(records)}"
            )
        expected_sources = set(cfg.expected_sources)
        actual_sources = {str(r.get("source_id")) for r in records if isinstance(r, dict)}
        if expected_sources and actual_sources != expected_sources:
            raise ValueError(
                f"Fast BESS expected sources {sorted(expected_sources)}, got {sorted(actual_sources)}"
            )

        for record in records:
            if not isinstance(record, dict):
                raise ValueError("Fast BESS shape error: each record must be an object")
            pcs = record.get("pcs_values")
            bms = record.get("bms_values")
            if not isinstance(pcs, dict) or not isinstance(bms, dict):
                raise ValueError("Fast BESS shape error: pcs_values/bms_values must be objects")
            if len(pcs) != cfg.expected_pcs_signal_count:
                raise ValueError(
                    f"Fast BESS {record.get('source_id')} expected {cfg.expected_pcs_signal_count} PCS signals, got {len(pcs)}"
                )
            if len(bms) != cfg.expected_bms_signal_count:
                raise ValueError(
                    f"Fast BESS {record.get('source_id')} expected {cfg.expected_bms_signal_count} BMS signals, got {len(bms)}"
                )
            if int(record.get("selected_signal_count") or 0) != (
                cfg.expected_pcs_signal_count + cfg.expected_bms_signal_count
            ):
                raise ValueError(
                    f"Fast BESS {record.get('source_id')} selected_signal_count mismatch"
                )

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.producer_config.enabled,
            "running": self.running,
            "started_utc": self.started_utc,
            "stream": self.producer_config.stream,
            "substream": self.producer_config.substream,
            "priority": self.producer_config.priority,
            "sample_interval_sec": self.producer_config.sample_interval_sec,
            "live_snapshot_path": self.producer_config.live_snapshot_path,
            "max_snapshot_age_sec": self.producer_config.max_snapshot_age_sec,
            "expected_bess_count": self.producer_config.expected_bess_count,
            "expected_pcs_signal_count": self.producer_config.expected_pcs_signal_count,
            "expected_bms_signal_count": self.producer_config.expected_bms_signal_count,
            "counters": self.counters.__dict__.copy(),
            "status_generated_utc": utc_now_iso(),
        }

    def _write_status(self) -> None:
        try:
            safe_write_json(self.producer_config.status_file, self.status())
        except Exception as exc:
            log.warning("failed to write Fast BESS producer status: %s", exc)


def _exc_text(exc: Exception) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except Exception:
        return None
