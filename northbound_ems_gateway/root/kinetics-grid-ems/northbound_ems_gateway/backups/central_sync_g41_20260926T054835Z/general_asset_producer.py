from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from nb_ems_gateway.dictionary.central_signal_policy import CentralSignalPolicy

from .config import CentralSyncConfig
from .contracts import make_message, utc_now_iso
from .general_asset_live_source import GeneralAssetLiveSource
from .outbox import OutboxStore
from .status import safe_write_json

log = logging.getLogger(__name__)

_ALLOWED_POLICIES = {
    "NORMAL_5S",
    "NORMAL_10S",
    "NORMAL_30S",
    "SLOW_60S",
    "ON_CHANGE_HEARTBEAT",
    "STATIC_ON_CHANGE",
}
_CHANGE_POLICIES = {"ON_CHANGE_HEARTBEAT", "STATIC_ON_CHANGE"}


@dataclass
class GeneralAssetProducerCounters:
    poll_count: int = 0
    poll_success_count: int = 0
    poll_failure_count: int = 0
    duplicate_snapshot_count: int = 0
    shape_rejection_count: int = 0
    enqueue_count: int = 0
    enqueue_failure_count: int = 0
    message_count: int = 0
    record_count: int = 0
    startup_record_count: int = 0
    change_record_count: int = 0
    heartbeat_record_count: int = 0
    periodic_record_count: int = 0
    last_poll_utc: str | None = None
    last_success_utc: str | None = None
    last_enqueue_utc: str | None = None
    last_error: str | None = None
    last_sampled_at_utc: str | None = None
    last_sampled_at_epoch_ms: int | None = None
    last_snapshot_age_sec: float | None = None
    last_message_ids: dict[str, str] = field(default_factory=dict)
    last_sequences: dict[str, int] = field(default_factory=dict)
    records_by_substream: dict[str, int] = field(default_factory=dict)
    records_by_policy: dict[str, int] = field(default_factory=dict)


class GeneralAssetProducer:
    """Produce S2 general asset telemetry from a volatile AssetManager snapshot.

    The source path is strictly live cache -> /run tmpfs snapshot -> this producer
    -> G1 durable outbox. This producer never opens the NorthBound historian DB
    and never performs Modbus reads.
    """

    def __init__(
        self,
        *,
        config: CentralSyncConfig,
        outbox: OutboxStore,
        source: GeneralAssetLiveSource | Any | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.producer_config = config.general_assets
        self.outbox = outbox
        self.policy = CentralSignalPolicy(self.producer_config.policy_manifest_path)
        self.source = source or GeneralAssetLiveSource(
            self.producer_config.live_snapshot_path,
            max_snapshot_age_sec=self.producer_config.max_snapshot_age_sec,
            expected_policy_sha256=self.policy.sha256,
        )
        self.clock = clock
        self.counters = GeneralAssetProducerCounters()
        self.running = False
        self.started_utc = utc_now_iso()
        self._stop = asyncio.Event()
        self._last_sampled_epoch_ms: int | None = None
        self._last_emitted_mono: dict[str, float] = {}
        self._last_fingerprint: dict[str, str] = {}

    async def close(self) -> None:
        return None

    async def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        if not self.producer_config.enabled:
            log.info("General asset producer disabled")
            return
        interval = max(0.2, float(self.producer_config.poll_interval_sec))
        self.running = True
        self._stop.clear()
        log.info(
            "General asset producer started poll=%.3fs source=%s policy=%s stream=%s",
            interval,
            self.producer_config.live_snapshot_path,
            self.producer_config.policy_manifest_path,
            self.producer_config.stream,
        )
        next_tick = self.clock()
        try:
            while not self._stop.is_set():
                delay = max(0.0, next_tick - self.clock())
                if delay:
                    try:
                        await asyncio.wait_for(self._stop.wait(), timeout=delay)
                        break
                    except asyncio.TimeoutError:
                        pass
                await self.collect_once()
                next_tick += interval
                if next_tick < self.clock() - interval:
                    next_tick = self.clock() + interval
        finally:
            self.running = False
            self._write_status()
            log.info("General asset producer stopped")

    async def collect_once(self) -> dict[str, Any]:
        now_utc = utc_now_iso()
        now_mono = self.clock()
        self.counters.poll_count += 1
        self.counters.last_poll_utc = now_utc

        try:
            snapshot = await asyncio.to_thread(self.source.read)
            self._validate_snapshot(snapshot)
        except Exception as exc:
            error = _exc_text(exc)
            self.counters.poll_failure_count += 1
            self.counters.last_error = error
            if any(x in error.lower() for x in ("shape", "expected", "mismatch", "contract")):
                self.counters.shape_rejection_count += 1
            self._write_status()
            log.warning("General asset live snapshot rejected: %s", error)
            return {
                "emitted": False,
                "reason": "source_error",
                "error": error,
                "outbox": self.outbox.stats(),
            }

        sampled_ms = int(snapshot["sampled_at_epoch_ms"])
        sampled_utc = str(snapshot.get("sampled_at_utc") or now_utc)
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

        due_by_substream: dict[str, list[dict[str, Any]]] = {}
        state_updates: dict[str, tuple[float, str, str]] = {}
        policy_due_counts: dict[str, int] = {}
        reason_counts: dict[str, int] = {}

        for runtime in self._iter_runtime_signals(snapshot):
            spec = runtime["spec"]
            policy_name = str(spec["policy"])
            runtime_key = str(runtime["runtime_signal_id"])
            fingerprint = _fingerprint(runtime.get("value"), runtime.get("quality"))
            reason = self._due_reason(
                runtime_key=runtime_key,
                policy_name=policy_name,
                record_sec=float(spec.get("central_record_sec") or 0.0),
                fingerprint=fingerprint,
                now_mono=now_mono,
            )
            if reason is None:
                continue

            substream = str(spec["substream"])
            record = self._build_record(
                runtime=runtime,
                sampled_utc=sampled_utc,
                snapshot_age_sec=snapshot.get("snapshot_age_sec"),
                reason=reason,
            )
            due_by_substream.setdefault(substream, []).append(record)
            state_updates[runtime_key] = (now_mono, fingerprint, reason)
            policy_due_counts[policy_name] = policy_due_counts.get(policy_name, 0) + 1
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        if not due_by_substream:
            self._last_sampled_epoch_ms = sampled_ms
            self.counters.last_sampled_at_utc = sampled_utc
            self.counters.last_sampled_at_epoch_ms = sampled_ms
            self._write_status()
            return {
                "emitted": False,
                "reason": "no_due_records",
                "sampled_at_utc": sampled_utc,
                "sampled_at_epoch_ms": sampled_ms,
                "outbox": self.outbox.stats(),
            }

        inserted_messages: list[dict[str, Any]] = []
        committed_keys: set[str] = set()

        # One logical message per S2 substream. This keeps backend routing and
        # sequence spaces independent across the nine asset families.
        for substream in sorted(due_by_substream):
            records = due_by_substream[substream]
            sequence = self.outbox.next_sequence(self.producer_config.stream, substream)
            message = make_message(
                schema_version=self.config.identity.schema_version,
                gateway_id=self.config.identity.gateway_id,
                site_id=self.config.identity.site_id,
                stream=self.producer_config.stream,
                substream=substream,
                sequence=sequence,
                priority=self.producer_config.priority,
                records=records,
                created_at_utc=sampled_utc,
            )
            try:
                inserted = self.outbox.enqueue(message)
            except Exception as exc:
                self.counters.enqueue_failure_count += 1
                self.counters.last_error = f"outbox enqueue failed: {_exc_text(exc)}"
                self._write_status()
                raise
            if not inserted:
                continue

            for record in records:
                committed_keys.add(str(record["runtime_signal_id"]))
            self.counters.enqueue_count += 1
            self.counters.message_count += 1
            self.counters.record_count += len(records)
            self.counters.last_message_ids[substream] = message.message_id
            self.counters.last_sequences[substream] = sequence
            self.counters.records_by_substream[substream] = (
                self.counters.records_by_substream.get(substream, 0) + len(records)
            )
            inserted_messages.append({
                "substream": substream,
                "sequence": sequence,
                "message_id": message.message_id,
                "record_count": len(records),
            })

        for key in committed_keys:
            emit_mono, fingerprint, reason = state_updates[key]
            self._last_emitted_mono[key] = emit_mono
            self._last_fingerprint[key] = fingerprint
            if reason == "startup":
                self.counters.startup_record_count += 1
            elif reason == "change":
                self.counters.change_record_count += 1
            elif reason == "heartbeat":
                self.counters.heartbeat_record_count += 1
            elif reason == "periodic":
                self.counters.periodic_record_count += 1

        for policy_name, count in policy_due_counts.items():
            # Only count records belonging to successfully inserted substreams.
            # All substream inserts are expected to succeed in normal operation.
            self.counters.records_by_policy[policy_name] = (
                self.counters.records_by_policy.get(policy_name, 0) + count
            )

        self._last_sampled_epoch_ms = sampled_ms
        self.counters.last_enqueue_utc = now_utc if inserted_messages else self.counters.last_enqueue_utc
        self.counters.last_sampled_at_utc = sampled_utc
        self.counters.last_sampled_at_epoch_ms = sampled_ms
        self._write_status()

        return {
            "emitted": bool(inserted_messages),
            "message_count": len(inserted_messages),
            "record_count": sum(x["record_count"] for x in inserted_messages),
            "messages": inserted_messages,
            "policy_due_counts": policy_due_counts,
            "reason_counts": reason_counts,
            "sampled_at_utc": sampled_utc,
            "sampled_at_epoch_ms": sampled_ms,
            "snapshot_age_sec": snapshot.get("snapshot_age_sec"),
            "outbox": self.outbox.stats(),
        }

    def _iter_runtime_signals(self, snapshot: dict[str, Any]):
        for asset_record in snapshot.get("records") or []:
            source_id = str(asset_record.get("source_id") or "")
            runtime_asset_id = str(asset_record.get("runtime_asset_id") or "")
            base_asset_id = str(asset_record.get("base_asset_id") or "")
            substream = str(asset_record.get("substream") or "")
            signals = asset_record.get("signals") or {}
            for signal_name, signal in signals.items():
                point_id = str((signal or {}).get("point_id") or "")
                spec = self.policy.by_point_id.get(point_id)
                if spec is None:
                    raise ValueError(f"S2 contract shape: unknown point_id {point_id!r}")
                if spec.get("primary_stream") != "S2 general_asset_telemetry":
                    raise ValueError(f"S2 contract shape: non-S2 point present {point_id}")
                if str(spec.get("asset")) != base_asset_id:
                    raise ValueError(f"S2 contract shape: asset mismatch for {point_id}")
                if str(spec.get("signal")) != str(signal_name):
                    raise ValueError(f"S2 contract shape: signal mismatch for {point_id}")
                if str(spec.get("substream")) != substream:
                    raise ValueError(f"S2 contract shape: substream mismatch for {point_id}")
                yield {
                    "source_id": source_id,
                    "runtime_asset_id": runtime_asset_id,
                    "base_asset_id": base_asset_id,
                    "substream": substream,
                    "signal_name": str(signal_name),
                    "point_id": point_id,
                    "value": (signal or {}).get("value"),
                    "quality": (signal or {}).get("quality"),
                    "updated_utc": (signal or {}).get("updated_utc"),
                    "age_ms": (signal or {}).get("age_ms"),
                    "runtime_signal_id": f"{source_id}.{base_asset_id}.{signal_name}",
                    "spec": spec,
                }

    def _due_reason(
        self,
        *,
        runtime_key: str,
        policy_name: str,
        record_sec: float,
        fingerprint: str,
        now_mono: float,
    ) -> str | None:
        if policy_name not in _ALLOWED_POLICIES:
            raise ValueError(f"unsupported S2 policy: {policy_name}")
        last_emit = self._last_emitted_mono.get(runtime_key)
        last_fingerprint = self._last_fingerprint.get(runtime_key)
        if last_emit is None or last_fingerprint is None:
            return "startup"
        elapsed = max(0.0, now_mono - last_emit)
        if policy_name in _CHANGE_POLICIES:
            if fingerprint != last_fingerprint:
                return "change"
            if record_sec > 0 and elapsed >= record_sec:
                return "heartbeat"
            return None
        if record_sec > 0 and elapsed >= record_sec:
            return "periodic"
        return None

    def _build_record(
        self,
        *,
        runtime: dict[str, Any],
        sampled_utc: str,
        snapshot_age_sec: Any,
        reason: str,
    ) -> dict[str, Any]:
        spec = runtime["spec"]
        return {
            "record_type": "general_asset_signal",
            "sample_source": "asset_manager_live_cache",
            "persisted_source": False,
            "observed_at_utc": sampled_utc,
            "source_updated_utc": runtime.get("updated_utc"),
            "snapshot_age_sec": snapshot_age_sec,
            "source_data_age_ms": runtime.get("age_ms"),
            "source_id": runtime["source_id"],
            "runtime_asset_id": runtime["runtime_asset_id"],
            "base_asset_id": runtime["base_asset_id"],
            "substream": runtime["substream"],
            "runtime_signal_id": runtime["runtime_signal_id"],
            "point_id": runtime["point_id"],
            "signal": runtime["signal_name"],
            "display_name": spec.get("display_name"),
            "value": runtime.get("value"),
            "unit": spec.get("unit"),
            "category": spec.get("category"),
            "quality": runtime.get("quality"),
            "policy": spec.get("policy"),
            "central_record_sec": spec.get("central_record_sec"),
            "upload_batch_sec": spec.get("upload_batch_sec"),
            "signal_priority": spec.get("signal_priority"),
            "retention_class": spec.get("retention_class"),
            "rw": spec.get("rw"),
            "key_signal": spec.get("key_signal"),
            "trigger_reason": reason,
        }

    def _validate_snapshot(self, snapshot: dict[str, Any]) -> None:
        cfg = self.producer_config
        if snapshot.get("sample_source") != "asset_manager_live_cache":
            raise ValueError("S2 contract shape: source is not live AssetManager cache")
        if snapshot.get("persisted_source") is not False:
            raise ValueError("S2 contract shape: persisted_source must be false")
        if str(snapshot.get("policy_manifest_sha256") or "") != self.policy.sha256:
            raise ValueError("S2 contract shape: policy manifest hash mismatch")
        records = snapshot.get("records")
        if not isinstance(records, list):
            raise ValueError("S2 contract shape: records must be a list")
        if not cfg.strict_shape:
            return

        if int(snapshot.get("source_count") or 0) != cfg.expected_source_count:
            raise ValueError(
                f"S2 expected source_count={cfg.expected_source_count}, got {snapshot.get('source_count')}"
            )
        if int(snapshot.get("asset_record_count") or 0) != cfg.expected_asset_record_count:
            raise ValueError(
                f"S2 expected asset_record_count={cfg.expected_asset_record_count}, got {snapshot.get('asset_record_count')}"
            )
        if int(snapshot.get("s2_canonical_signal_count") or 0) != cfg.expected_s2_canonical_count:
            raise ValueError(
                f"S2 expected canonical_count={cfg.expected_s2_canonical_count}, got {snapshot.get('s2_canonical_signal_count')}"
            )
        if int(snapshot.get("s2_runtime_signal_count") or 0) != cfg.expected_s2_runtime_count:
            raise ValueError(
                f"S2 expected runtime_count={cfg.expected_s2_runtime_count}, got {snapshot.get('s2_runtime_signal_count')}"
            )
        if len(records) != cfg.expected_asset_record_count:
            raise ValueError(f"S2 expected {cfg.expected_asset_record_count} asset records, got {len(records)}")

        expected_sources = set(cfg.expected_sources)
        actual_sources = {str(r.get("source_id")) for r in records}
        if expected_sources and actual_sources != expected_sources:
            raise ValueError(
                f"S2 expected sources {sorted(expected_sources)}, got {sorted(actual_sources)}"
            )

        total_signals = 0
        point_occurrences: dict[str, int] = {}
        for record in records:
            signals = record.get("signals")
            if not isinstance(signals, dict):
                raise ValueError("S2 contract shape: asset signals must be an object")
            if int(record.get("selected_signal_count") or 0) != len(signals):
                raise ValueError("S2 contract shape: selected_signal_count mismatch")
            total_signals += len(signals)
            for sig in signals.values():
                point_id = str((sig or {}).get("point_id") or "")
                point_occurrences[point_id] = point_occurrences.get(point_id, 0) + 1

        if total_signals != cfg.expected_s2_runtime_count:
            raise ValueError(
                f"S2 expected {cfg.expected_s2_runtime_count} runtime signals, got {total_signals}"
            )
        expected_point_ids = {x["point_id"] for x in self.policy.s2_signals}
        if set(point_occurrences) != expected_point_ids:
            raise ValueError("S2 contract shape: runtime point IDs do not cover exact S2 canonical set")
        for point_id, count in point_occurrences.items():
            if count != cfg.expected_source_count:
                raise ValueError(
                    f"S2 contract shape: point {point_id} expected {cfg.expected_source_count} runtime instances, got {count}"
                )

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.producer_config.enabled,
            "running": self.running,
            "started_utc": self.started_utc,
            "stream": self.producer_config.stream,
            "priority": self.producer_config.priority,
            "poll_interval_sec": self.producer_config.poll_interval_sec,
            "live_snapshot_path": self.producer_config.live_snapshot_path,
            "policy_manifest_path": self.producer_config.policy_manifest_path,
            "policy_manifest_sha256": self.policy.sha256,
            "expected_source_count": self.producer_config.expected_source_count,
            "expected_asset_record_count": self.producer_config.expected_asset_record_count,
            "expected_s2_canonical_count": self.producer_config.expected_s2_canonical_count,
            "expected_s2_runtime_count": self.producer_config.expected_s2_runtime_count,
            "substreams": self.policy.s2_substreams,
            "counters": self.counters.__dict__.copy(),
            "status_generated_utc": utc_now_iso(),
        }

    def _write_status(self) -> None:
        try:
            safe_write_json(self.producer_config.status_file, self.status())
        except Exception as exc:
            log.warning("failed to write General Asset producer status: %s", exc)


def _fingerprint(value: Any, quality: Any) -> str:
    # JSON gives deterministic behavior for None/bool/number/string and avoids
    # float NaN comparing unequal to itself forever.
    if isinstance(value, float) and math.isnan(value):
        value = "NaN"
    return json.dumps([value, quality], sort_keys=True, separators=(",", ":"), default=str)


def _exc_text(exc: Exception) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except Exception:
        return None
