from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import CentralSyncConfig
from .contracts import make_message, utc_now_iso
from .outbox import OutboxCapacityError, OutboxStore
from .status import safe_write_json

log = logging.getLogger(__name__)


@dataclass
class EdgeAIProducerCounters:
    poll_count: int = 0
    poll_success_count: int = 0
    poll_failure_count: int = 0
    unique_cycle_count: int = 0
    duplicate_cycle_count: int = 0
    inference_message_count: int = 0
    anomaly_message_count: int = 0
    anomaly_record_count: int = 0
    status_transition_count: int = 0
    status_heartbeat_count: int = 0
    stale_observation_count: int = 0
    enqueue_failure_count: int = 0
    last_poll_utc: str | None = None
    last_success_utc: str | None = None
    last_enqueue_utc: str | None = None
    last_error: str | None = None
    last_message_id: str | None = None
    last_sequence: int | None = None
    last_cycle_index: int | None = None
    last_cycle_time: str | None = None
    last_reason: str | None = None


class EdgeAIProducer:
    """S7 producer for Edge-AI inference and anomaly forensic context.

    This producer is deliberately file-fed. It reads the existing Edge-AI latest
    result plus its model manifest and never performs device/Modbus reads or ML
    inference itself. Each unique Edge-AI cycle is forwarded once. A status
    transition/heartbeat can be emitted while a cycle is unchanged (for example
    when the latest inference becomes stale). Full 33-feature vectors are carried
    only inside anomaly-context records.
    """

    def __init__(self, *, config: CentralSyncConfig, outbox: OutboxStore) -> None:
        self.config = config
        self.producer_config = config.edge_ai
        self.outbox = outbox
        self.counters = EdgeAIProducerCounters()
        self.running = False
        self.started_utc = utc_now_iso()
        self._stop = asyncio.Event()
        self._state = self._load_state()

    async def close(self) -> None:
        return None

    async def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        if not self.producer_config.enabled:
            log.info("S7 Edge-AI producer disabled")
            return
        self.running = True
        self._stop.clear()
        log.info(
            "S7 Edge-AI producer started poll=%.1fs stale=%.1fs stream=%s/%s",
            self.producer_config.poll_interval_sec,
            self.producer_config.stale_after_sec,
            self.producer_config.stream,
            self.producer_config.substream,
        )
        try:
            while not self._stop.is_set():
                await self.collect_once()
                try:
                    await asyncio.wait_for(
                        self._stop.wait(),
                        timeout=max(0.2, self.producer_config.poll_interval_sec),
                    )
                except asyncio.TimeoutError:
                    pass
        finally:
            self.running = False
            self._write_status()
            log.info("S7 Edge-AI producer stopped")

    async def collect_once(self, *, force_emit: bool = False, reason: str | None = None) -> dict[str, Any]:
        now_utc = utc_now_iso()
        self.counters.poll_count += 1
        self.counters.last_poll_utc = now_utc

        read_error: str | None = None
        latest: dict[str, Any] = {}
        manifest: dict[str, Any] = {}
        try:
            latest, manifest = await asyncio.to_thread(self._read_sources)
            self.counters.poll_success_count += 1
            self.counters.last_success_utc = now_utc
            self.counters.last_error = None
        except Exception as exc:
            self.counters.poll_failure_count += 1
            read_error = _exc_text(exc)
            self.counters.last_error = read_error
            log.warning("S7 source read failed: %s", read_error)

        record = _normalize_inference(
            latest,
            manifest,
            observed_at_utc=now_utc,
            stale_after_sec=self.producer_config.stale_after_sec,
            read_error=read_error,
        )
        cycle_key = _cycle_key(record)
        previous_cycle_key = self._state.get("last_cycle_key")
        is_new_cycle = bool(cycle_key and cycle_key != previous_cycle_key)
        if is_new_cycle:
            self.counters.unique_cycle_count += 1
        elif cycle_key:
            self.counters.duplicate_cycle_count += 1

        if record.get("edge_ai_status") == "STALE":
            self.counters.stale_observation_count += 1

        status_fingerprint = _stable_hash(_status_semantics(record))
        previous_status_fingerprint = self._state.get("last_status_fingerprint")
        status_transition = (
            previous_status_fingerprint is not None
            and status_fingerprint != previous_status_fingerprint
        )
        heartbeat_due = _seconds_since(self._state.get("last_status_emit_utc"), now_utc) >= float(
            self.producer_config.status_heartbeat_interval_sec
        )

        inference_emitted = False
        inference_sequence: int | None = None
        anomaly_emitted = False
        anomaly_sequence: int | None = None
        anomaly_count = 0
        emit_reason = reason

        # Normal S7 path: each unique Edge-AI cycle goes upstream once. A manual
        # preview may force the current cycle without changing production state.
        if is_new_cycle or force_emit:
            anomaly_present = any(
                src.get("ml_predicted_anomaly") is True for src in (record.get("sources") or [])
            )
            priority = (
                self.producer_config.anomaly_priority
                if anomaly_present
                else self.producer_config.inference_priority
            )
            inference_sequence = await self._enqueue_records(
                records=[_public_inference_record(record)],
                priority=priority,
                created_at_utc=record.get("cycle_time") or now_utc,
            )
            if inference_sequence is not None:
                inference_emitted = True
                self.counters.inference_message_count += 1
                emit_reason = emit_reason or ("new_inference" if is_new_cycle else "manual")
                if cycle_key:
                    self._state["last_cycle_key"] = cycle_key
                    self._state["last_cycle_index"] = record.get("cycle_index")
                    self._state["last_cycle_time"] = record.get("cycle_time")
                    self.counters.last_cycle_index = _as_int(record.get("cycle_index"))
                    self.counters.last_cycle_time = _as_str(record.get("cycle_time"))

        # Anomaly forensic messages have their own per-source cursor. This means an
        # inference message can succeed while a transient anomaly-context enqueue
        # failure is retried safely on the next producer pass.
        anomaly_records: list[dict[str, Any]] = []
        if cycle_key:
            sent = dict(self._state.get("last_anomaly_cycle_by_source") or {})
            for src in record.get("sources") or []:
                if src.get("ml_predicted_anomaly") is not True:
                    continue
                sid = str(src.get("source_id") or "")
                if not sid or (sent.get(sid) == cycle_key and not force_emit):
                    continue
                context = _make_anomaly_context(
                    record=record,
                    source=src,
                    manifest=manifest,
                    expected_feature_count=self.producer_config.expected_feature_count,
                )
                if context is None:
                    # Never manufacture the 33-feature forensic vector. The normal
                    # inference is still sent; status exposes the exact enrichment gap.
                    self.counters.last_error = (
                        f"anomaly feature context incomplete for {sid}; expected "
                        f"{self.producer_config.expected_feature_count} features"
                    )
                    continue
                anomaly_records.append(context)

            if anomaly_records:
                anomaly_sequence = await self._enqueue_records(
                    records=anomaly_records,
                    priority=self.producer_config.anomaly_priority,
                    created_at_utc=record.get("cycle_time") or now_utc,
                )
                if anomaly_sequence is not None:
                    anomaly_emitted = True
                    anomaly_count = len(anomaly_records)
                    self.counters.anomaly_message_count += 1
                    self.counters.anomaly_record_count += anomaly_count
                    for item in anomaly_records:
                        sid = str(item.get("source_id") or "")
                        if sid:
                            sent[sid] = cycle_key
                    self._state["last_anomaly_cycle_by_source"] = sent

        # If the Edge-AI file stops advancing, still report a semantic health
        # transition (e.g. GOOD -> STALE) and a low-rate heartbeat. These records
        # retain the same inference content/cycle identity; they are not counted as
        # a new ML inference.
        if not (is_new_cycle or force_emit) and (status_transition or heartbeat_due):
            status_sequence = await self._enqueue_records(
                records=[_public_inference_record(record)],
                priority=(
                    self.producer_config.status_transition_priority
                    if status_transition
                    else self.producer_config.status_heartbeat_priority
                ),
                created_at_utc=now_utc,
            )
            if status_sequence is not None:
                inference_emitted = True
                inference_sequence = status_sequence
                self.counters.inference_message_count += 1
                if status_transition:
                    self.counters.status_transition_count += 1
                    emit_reason = "status_transition"
                else:
                    self.counters.status_heartbeat_count += 1
                    emit_reason = "status_heartbeat"
                self._state["last_status_emit_utc"] = now_utc

        self._state["last_status_fingerprint"] = status_fingerprint
        if inference_emitted and "last_status_emit_utc" not in self._state:
            self._state["last_status_emit_utc"] = now_utc
        if is_new_cycle and inference_emitted:
            self._state["last_status_emit_utc"] = now_utc
        self.counters.last_reason = emit_reason
        self.counters.last_cycle_index = _as_int(self._state.get("last_cycle_index"))
        self.counters.last_cycle_time = _as_str(self._state.get("last_cycle_time"))
        await asyncio.to_thread(self._save_state)
        self._write_status()

        return {
            "inference_emitted": inference_emitted,
            "inference_sequence": inference_sequence,
            "anomaly_emitted": anomaly_emitted,
            "anomaly_sequence": anomaly_sequence,
            "anomaly_count": anomaly_count,
            "new_cycle": is_new_cycle,
            "cycle_index": record.get("cycle_index"),
            "cycle_time": record.get("cycle_time"),
            "edge_ai_status": record.get("edge_ai_status"),
            "latest_age_sec": record.get("latest_age_sec"),
            "source_count": len(record.get("sources") or []),
            "outbox": await asyncio.to_thread(self.outbox.stats),
        }

    def _read_sources(self) -> tuple[dict[str, Any], dict[str, Any]]:
        latest = _read_json(self.producer_config.latest_json_path)
        manifest = _read_json(self.producer_config.model_manifest_path)
        return latest, manifest

    async def _enqueue_records(
        self,
        *,
        records: list[dict[str, Any]],
        priority: str,
        created_at_utc: str,
    ) -> int | None:
        sequence = await asyncio.to_thread(
            self.outbox.next_sequence,
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
            priority=priority,
            records=records,
            created_at_utc=created_at_utc,
        )
        try:
            inserted = await asyncio.to_thread(self.outbox.enqueue, message)
        except OutboxCapacityError as exc:
            self.counters.enqueue_failure_count += 1
            self.counters.last_error = f"outbox capacity backpressure: {_exc_text(exc)}"
            log.error("S7 paused by outbox capacity guard: %s", exc)
            return None
        except Exception as exc:
            self.counters.enqueue_failure_count += 1
            self.counters.last_error = f"outbox enqueue failed: {_exc_text(exc)}"
            raise
        if not inserted:
            return None
        self.counters.last_enqueue_utc = created_at_utc
        self.counters.last_message_id = message.message_id
        self.counters.last_sequence = sequence
        return sequence

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.producer_config.enabled,
            "running": self.running,
            "started_utc": self.started_utc,
            "stream": self.producer_config.stream,
            "substream": self.producer_config.substream,
            "poll_interval_sec": self.producer_config.poll_interval_sec,
            "stale_after_sec": self.producer_config.stale_after_sec,
            "latest_json_path": self.producer_config.latest_json_path,
            "model_manifest_path": self.producer_config.model_manifest_path,
            "state_file": self.producer_config.state_file,
            "last_cycle_key": self._state.get("last_cycle_key"),
            "counters": self.counters.__dict__.copy(),
            "status_generated_utc": utc_now_iso(),
        }

    def _load_state(self) -> dict[str, Any]:
        try:
            data = json.loads(Path(self.producer_config.state_file).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as exc:
            log.warning("S7 state load failed; starting empty: %s", exc)
            return {}

    def _save_state(self) -> None:
        safe_write_json(self.producer_config.state_file, self._state)

    def _write_status(self) -> None:
        try:
            safe_write_json(self.producer_config.status_file, self.status())
        except Exception as exc:
            log.warning("failed to write S7 producer status: %s", exc)


def _read_json(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def _normalize_inference(
    latest: dict[str, Any],
    manifest: dict[str, Any],
    *,
    observed_at_utc: str,
    stale_after_sec: float,
    read_error: str | None,
) -> dict[str, Any]:
    model_raw = latest.get("model_info") if isinstance(latest.get("model_info"), dict) else {}
    manifest_features = manifest.get("features") if isinstance(manifest.get("features"), list) else []
    cycle_time = _as_str(latest.get("cycle_time"))
    age = _age_sec(cycle_time, observed_at_utc)
    source_map = latest.get("sources") if isinstance(latest.get("sources"), dict) else {}

    sources: list[dict[str, Any]] = []
    for source_key in sorted(source_map):
        raw = source_map.get(source_key)
        if not isinstance(raw, dict):
            continue
        kf = raw.get("key_features") if isinstance(raw.get("key_features"), dict) else {}
        fv = raw.get("feature_vector") if isinstance(raw.get("feature_vector"), dict) else {}
        sources.append({
            "ok": raw.get("ok"),
            "source_id": raw.get("source_id") or source_key,
            "bess_id": raw.get("bess_id"),
            "ml_predicted_anomaly": raw.get("ml_predicted_anomaly"),
            "anomaly_score_ml": raw.get("anomaly_score_ml"),
            "threshold": raw.get("threshold", model_raw.get("threshold", manifest.get("threshold"))),
            "inference_latency_ms": raw.get("inference_latency_ms"),
            "key_features": {str(k): v for k, v in kf.items()},
            # Kept internal to Central Sync normalization; the normal inference
            # record strips this before enqueue. It is available to build anomaly
            # forensic context only.
            "_feature_vector": {str(k): v for k, v in fv.items()},
        })

    if read_error:
        edge_status = "ERROR"
    elif age is None:
        edge_status = "ERROR"
    elif age > float(stale_after_sec):
        edge_status = "STALE"
    elif not sources:
        edge_status = "ERROR"
    elif all(src.get("ok") is True for src in sources):
        edge_status = "GOOD"
    else:
        edge_status = "DEGRADED"

    public_sources = []
    for src in sources:
        public_sources.append({k: v for k, v in src.items() if not k.startswith("_")})

    return {
        "phase": latest.get("phase"),
        "cycle_time": cycle_time,
        "cycle_index": latest.get("cycle_index"),
        "cycle_latency_ms": latest.get("cycle_latency_ms"),
        "model_info": {
            "version": manifest.get("version") or model_raw.get("version"),
            "model_type": model_raw.get("model_type") or manifest.get("model_type"),
            "feature_count": (
                manifest.get("feature_count")
                if manifest.get("feature_count") is not None
                else (len(manifest_features) or model_raw.get("feature_count"))
            ),
            "threshold": (
                model_raw.get("threshold")
                if model_raw.get("threshold") is not None
                else manifest.get("threshold")
            ),
            "threshold_direction": manifest.get("threshold_direction") or model_raw.get("threshold_direction"),
        },
        "edge_ai_status": edge_status,
        "latest_age_sec": age,
        "stale_after_sec": float(stale_after_sec),
        "sources": public_sources,
        # Internal-only parallel map for anomaly-context generation.
        "_source_feature_vectors": {
            str(src.get("source_id") or ""): src.get("_feature_vector") or {}
            for src in sources
            if src.get("source_id")
        },
    }


def _public_inference_record(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if not k.startswith("_")}


def _make_anomaly_context(
    *,
    record: dict[str, Any],
    source: dict[str, Any],
    manifest: dict[str, Any],
    expected_feature_count: int,
) -> dict[str, Any] | None:
    sid = str(source.get("source_id") or "")
    feature_vectors = record.get("_source_feature_vectors") or {}
    features = feature_vectors.get(sid) if isinstance(feature_vectors, dict) else None
    if not isinstance(features, dict) or len(features) != int(expected_feature_count):
        return None

    # Contract uses the exact 33 manifest feature names. Keep manifest ordering in
    # the serialized dict for human readability while backend JSON semantics remain
    # name based.
    ordered: dict[str, Any] = {}
    names = manifest.get("features") if isinstance(manifest.get("features"), list) else list(features)
    for name in names:
        if name not in features:
            return None
        ordered[str(name)] = features[name]

    model_info = record.get("model_info") or {}
    return {
        "phase": record.get("phase"),
        "cycle_time": record.get("cycle_time"),
        "cycle_index": record.get("cycle_index"),
        "source_id": source.get("source_id"),
        "bess_id": source.get("bess_id"),
        "ml_predicted_anomaly": True,
        "anomaly_score_ml": source.get("anomaly_score_ml"),
        "anomaly_context": {
            "features": ordered,
            "model_version": model_info.get("version"),
            "threshold": source.get("threshold", model_info.get("threshold")),
            "raw_sample_timestamp_utc": None,
            "fast_bess_sample_id": None,
            "reason": None,
        },
    }


def _cycle_key(record: dict[str, Any]) -> str | None:
    cycle_time = record.get("cycle_time")
    cycle_index = record.get("cycle_index")
    if cycle_time is None and cycle_index is None:
        return None
    return f"{cycle_time}|{cycle_index}"


def _status_semantics(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "edge_ai_status": record.get("edge_ai_status"),
        "model_info": record.get("model_info"),
        "source_health": [
            {
                "source_id": src.get("source_id"),
                "ok": src.get("ok"),
                "ml_predicted_anomaly": src.get("ml_predicted_anomaly"),
            }
            for src in (record.get("sources") or [])
        ],
    }


def _age_sec(then_utc: Any, now_utc: str) -> float | None:
    if not then_utc:
        return None
    try:
        then = _parse_dt(str(then_utc))
        now = _parse_dt(now_utc)
        return round(max(0.0, (now - then).total_seconds()), 3)
    except Exception:
        return None


def _seconds_since(then_utc: Any, now_utc: str) -> float:
    if not then_utc:
        return float("inf")
    try:
        return max(0.0, (_parse_dt(now_utc) - _parse_dt(str(then_utc))).total_seconds())
    except Exception:
        return float("inf")


def _parse_dt(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _exc_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__
