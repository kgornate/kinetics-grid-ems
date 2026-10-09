from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from .config import CentralSyncConfig
from .contracts import PRIORITY_RANK, make_message, utc_now_iso
from .fast_bess_live_source import FastBESSLiveSource
from .general_asset_live_source import GeneralAssetLiveSource
from .outbox import OutboxCapacityError, OutboxStore
from .status import safe_write_json

log = logging.getLogger(__name__)


@dataclass
class AlarmEventProducerCounters:
    poll_count: int = 0
    poll_success_count: int = 0
    poll_failure_count: int = 0
    general_snapshot_success_count: int = 0
    general_snapshot_failure_count: int = 0
    fast_snapshot_success_count: int = 0
    fast_snapshot_failure_count: int = 0
    baseline_signal_count: int = 0
    evaluated_signal_count: int = 0
    ignored_missing_value_count: int = 0
    ignored_bad_quality_count: int = 0
    suppressed_same_state_count: int = 0
    active_event_count: int = 0
    cleared_event_count: int = 0
    active_value_change_count: int = 0
    enqueue_count: int = 0
    enqueue_failure_count: int = 0
    event_record_count: int = 0
    last_poll_utc: str | None = None
    last_success_utc: str | None = None
    last_enqueue_utc: str | None = None
    last_error: str | None = None
    last_message_id: str | None = None
    last_sequence: int | None = None


class AlarmEventProducer:
    """Produce S4 alarms_events from live S1/S2 cache snapshots.

    Contract source:
      Central_Sync_9_Stream_Data_Contract_FROZEN_v1_1...
      -> S4 Event Trigger Catalog
      -> frozen JSON trigger manifest

    Data source is deliberately RAM-only:
      /run/nb-ems/general_asset_live.json  (S2 event-capable points)
      /run/nb-ems/fast_bess_live.json      (S1 event-capable points)

    No Modbus reads, historian reads, or NorthBound HTTP requests are performed.
    The producer stores only compact transition state under /var/lib so repeated
    identical active alarms are not re-emitted after a Central Sync restart.
    """

    def __init__(
        self,
        *,
        config: CentralSyncConfig,
        outbox: OutboxStore,
        general_source: GeneralAssetLiveSource | Any | None = None,
        fast_source: FastBESSLiveSource | Any | None = None,
    ) -> None:
        self.config = config
        self.producer_config = config.alarms_events
        self.outbox = outbox
        self.general_source = general_source or GeneralAssetLiveSource(
            self.producer_config.general_snapshot_path,
            max_snapshot_age_sec=self.producer_config.max_snapshot_age_sec,
        )
        self.fast_source = fast_source or FastBESSLiveSource(
            self.producer_config.fast_bess_snapshot_path,
            max_snapshot_age_sec=self.producer_config.max_snapshot_age_sec,
        )
        self._manifest = self._load_manifest(self.producer_config.trigger_manifest_path)
        self._trigger_by_point_id = {
            str(item["point_id"]): item for item in self._manifest["triggers"]
        }
        self._s1_triggers = [
            item
            for item in self._manifest["triggers"]
            if item.get("primary_telemetry_stream") == "S1 fast_bess_telemetry"
        ]
        self._s2_point_ids = {
            str(item["point_id"])
            for item in self._manifest["triggers"]
            if item.get("primary_telemetry_stream") == "S2 general_asset_telemetry"
        }
        self._validate_manifest()
        self._state: dict[str, dict[str, Any]] = self._load_state()
        self.counters = AlarmEventProducerCounters()
        self.running = False
        self.started_utc = utc_now_iso()
        self._stop = asyncio.Event()

    async def close(self) -> None:
        return None

    async def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        if not self.producer_config.enabled:
            log.info("S4 alarms/events producer disabled")
            return

        interval = max(0.2, float(self.producer_config.poll_interval_sec))
        self.running = True
        self._stop.clear()
        log.info(
            "S4 alarms/events producer started poll=%.3fs triggers=%d runtime=%d stream=%s",
            interval,
            len(self._trigger_by_point_id),
            int(self._manifest.get("runtime_trigger_count") or 0),
            self.producer_config.stream,
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
            log.info("S4 alarms/events producer stopped")

    async def collect_once(self) -> dict[str, Any]:
        now_utc = utc_now_iso()
        self.counters.poll_count += 1
        self.counters.last_poll_utc = now_utc

        observations: list[dict[str, Any]] = []
        source_errors: list[str] = []

        # S2-derived event candidates.
        try:
            general = await asyncio.to_thread(self.general_source.read)
            observations.extend(self._observations_from_general(general))
            self.counters.general_snapshot_success_count += 1
        except Exception as exc:
            self.counters.general_snapshot_failure_count += 1
            source_errors.append(f"general:{_exc_text(exc)}")

        # S1-only fast BESS event candidates.
        try:
            fast = await asyncio.to_thread(self.fast_source.read)
            observations.extend(self._observations_from_fast(fast))
            self.counters.fast_snapshot_success_count += 1
        except Exception as exc:
            self.counters.fast_snapshot_failure_count += 1
            source_errors.append(f"fast:{_exc_text(exc)}")

        if not observations:
            self.counters.poll_failure_count += 1
            self.counters.last_error = "; ".join(source_errors) or "no live event observations"
            self._write_status()
            log.warning("S4 event sources unavailable: %s", self.counters.last_error)
            return {
                "emitted": False,
                "reason": "source_error",
                "errors": source_errors,
                "outbox": await asyncio.to_thread(self.outbox.stats),
            }

        self.counters.poll_success_count += 1
        self.counters.last_success_utc = now_utc
        self.counters.last_error = "; ".join(source_errors) if source_errors else None

        events: list[dict[str, Any]] = []
        proposed_state = {key: dict(value) for key, value in self._state.items()}
        baseline_count = 0

        for obs in observations:
            self.counters.evaluated_signal_count += 1
            value = _normalize_enum_value(obs.get("value"))
            if value is None:
                self.counters.ignored_missing_value_count += 1
                continue

            quality = str(obs.get("quality") or "good").lower()
            if quality not in {"good", "ok", "valid", "unknown"}:
                self.counters.ignored_bad_quality_count += 1
                continue

            trigger = obs["trigger"]
            active_values = {_normalize_enum_value(v) for v in trigger.get("active_values") or []}
            is_active = value in active_values
            runtime_key = str(obs["runtime_signal_id"])
            previous = proposed_state.get(runtime_key)

            if previous is None:
                correlation_id = str(uuid4()) if is_active else None
                proposed_state[runtime_key] = {
                    "active": bool(is_active),
                    "value": value,
                    "correlation_id": correlation_id,
                    "last_observed_utc": obs["observed_at_utc"],
                }
                baseline_count += 1
                if is_active and self.producer_config.startup_emit_active:
                    events.append(
                        self._build_event(
                            obs=obs,
                            state="ACTIVE",
                            previous_value=None,
                            current_value=value,
                            correlation_id=correlation_id or str(uuid4()),
                            reason="startup_active",
                        )
                    )
                continue

            was_active = bool(previous.get("active"))
            previous_value = _normalize_enum_value(previous.get("value"))
            correlation_id = previous.get("correlation_id")

            if not was_active and is_active:
                correlation_id = str(uuid4())
                events.append(
                    self._build_event(
                        obs=obs,
                        state="ACTIVE",
                        previous_value=previous_value,
                        current_value=value,
                        correlation_id=correlation_id,
                        reason="activation",
                    )
                )
            elif was_active and not is_active:
                events.append(
                    self._build_event(
                        obs=obs,
                        state="CLEARED",
                        previous_value=previous_value,
                        current_value=value,
                        correlation_id=str(correlation_id or uuid4()),
                        reason="clear",
                    )
                )
                correlation_id = None
            elif was_active and is_active and previous_value != value:
                # A change from one active vendor alarm code to another is a
                # meaningful transition, but it remains in the same lifecycle.
                if not correlation_id:
                    correlation_id = str(uuid4())
                events.append(
                    self._build_event(
                        obs=obs,
                        state="ACTIVE",
                        previous_value=previous_value,
                        current_value=value,
                        correlation_id=str(correlation_id),
                        reason="active_value_change",
                    )
                )
            else:
                self.counters.suppressed_same_state_count += 1

            proposed_state[runtime_key] = {
                "active": bool(is_active),
                "value": value,
                "correlation_id": correlation_id,
                "last_observed_utc": obs["observed_at_utc"],
            }

        self.counters.baseline_signal_count += baseline_count

        if not events:
            # Keep the current observation state in RAM. Persist only when new
            # runtime signals are first baselined; steady-state 1 s polling must
            # not rewrite the lifecycle JSON continuously to eMMC.
            self._state = proposed_state
            if baseline_count:
                await asyncio.to_thread(self._save_state)
            self._write_status()
            return {
                "emitted": False,
                "reason": "no_transition",
                "observations": len(observations),
                "baseline_count": baseline_count,
                "source_errors": source_errors,
                "outbox": await asyncio.to_thread(self.outbox.stats),
            }

        priority = min(
            (self._priority_for_severity(str(event["severity"])) for event in events),
            key=lambda value: PRIORITY_RANK[value],
        )
        sequence = await asyncio.to_thread(
            self.outbox.next_sequence,
            self.producer_config.stream,
            None,
        )
        message = make_message(
            schema_version=self.config.identity.schema_version,
            gateway_id=self.config.identity.gateway_id,
            site_id=self.config.identity.site_id,
            stream=self.producer_config.stream,
            substream=None,
            sequence=sequence,
            priority=priority,
            records=events,
            created_at_utc=now_utc,
        )

        try:
            inserted = await asyncio.to_thread(self.outbox.enqueue, message)
        except OutboxCapacityError as exc:
            self.counters.enqueue_failure_count += 1
            self.counters.last_error = f"outbox capacity backpressure: {_exc_text(exc)}"
            self._write_status()
            log.error("S4 paused by outbox capacity guard: %s", exc)
            return {
                "emitted": False,
                "reason": "outbox_capacity",
                "error": str(exc),
                "event_count": len(events),
                "outbox": await asyncio.to_thread(self.outbox.stats),
            }
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
                "event_count": len(events),
                "outbox": await asyncio.to_thread(self.outbox.stats),
            }

        # Only commit lifecycle state after the event message is durable.
        self._state = proposed_state
        await asyncio.to_thread(self._save_state)

        self.counters.enqueue_count += 1
        self.counters.event_record_count += len(events)
        self.counters.active_event_count += sum(1 for x in events if x["state"] == "ACTIVE")
        self.counters.cleared_event_count += sum(1 for x in events if x["state"] == "CLEARED")
        self.counters.active_value_change_count += sum(
            1 for x in events if (x.get("payload") or {}).get("trigger_reason") == "active_value_change"
        )
        self.counters.last_enqueue_utc = now_utc
        self.counters.last_message_id = message.message_id
        self.counters.last_sequence = sequence
        self._write_status()

        log.info(
            "S4 event message enqueued sequence=%d events=%d priority=%s",
            sequence,
            len(events),
            priority,
        )
        return {
            "emitted": True,
            "message_id": message.message_id,
            "sequence": sequence,
            "priority": priority,
            "event_count": len(events),
            "states": {
                "ACTIVE": sum(1 for x in events if x["state"] == "ACTIVE"),
                "CLEARED": sum(1 for x in events if x["state"] == "CLEARED"),
            },
            "source_errors": source_errors,
            "outbox": await asyncio.to_thread(self.outbox.stats),
        }

    def _observations_from_general(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        sampled_utc = str(snapshot.get("sampled_at_utc") or utc_now_iso())
        snapshot_age = snapshot.get("snapshot_age_sec")
        observations: list[dict[str, Any]] = []
        for asset_record in snapshot.get("records") or []:
            source_id = str(asset_record.get("source_id") or "")
            runtime_asset_id = str(asset_record.get("runtime_asset_id") or "")
            base_asset_id = str(asset_record.get("base_asset_id") or "")
            for signal_name, raw_signal in (asset_record.get("signals") or {}).items():
                signal = raw_signal or {}
                point_id = str(signal.get("point_id") or "")
                if point_id not in self._s2_point_ids:
                    continue
                trigger = self._trigger_by_point_id[point_id]
                observations.append(
                    {
                        "trigger": trigger,
                        "source_id": source_id,
                        "runtime_asset_id": runtime_asset_id,
                        "base_asset_id": base_asset_id,
                        "signal_name": str(signal_name),
                        "runtime_signal_id": f"{source_id}.{base_asset_id}.{signal_name}",
                        "value": signal.get("value"),
                        "quality": signal.get("quality"),
                        "source_updated_utc": signal.get("updated_utc"),
                        "observed_at_utc": signal.get("updated_utc") or sampled_utc,
                        "sampled_at_utc": sampled_utc,
                        "snapshot_age_sec": snapshot_age,
                        "sample_source": "general_asset_live",
                    }
                )
        return observations

    def _observations_from_fast(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        sampled_utc = str(snapshot.get("sampled_at_utc") or utc_now_iso())
        snapshot_age = snapshot.get("snapshot_age_sec")
        observations: list[dict[str, Any]] = []
        for record in snapshot.get("records") or []:
            source_id = str(record.get("source_id") or "")
            for trigger in self._s1_triggers:
                base_asset_id = str(trigger["asset"])
                signal_name = str(trigger["signal"])
                if base_asset_id == "pcs_1":
                    values = record.get("pcs_values") or {}
                    runtime_asset_id = str(record.get("pcs_asset_id") or f"{source_id}_pcs")
                elif base_asset_id == "bms_1":
                    values = record.get("bms_values") or {}
                    runtime_asset_id = str(record.get("bms_asset_id") or f"{source_id}_bms")
                else:
                    continue
                if signal_name not in values:
                    continue
                observations.append(
                    {
                        "trigger": trigger,
                        "source_id": source_id,
                        "runtime_asset_id": runtime_asset_id,
                        "base_asset_id": base_asset_id,
                        "signal_name": signal_name,
                        "runtime_signal_id": f"{source_id}.{base_asset_id}.{signal_name}",
                        "value": values.get(signal_name),
                        "quality": record.get("quality") or "good",
                        "source_updated_utc": None,
                        "observed_at_utc": sampled_utc,
                        "sampled_at_utc": sampled_utc,
                        "snapshot_age_sec": snapshot_age,
                        "sample_source": "fast_bess_live",
                    }
                )
        return observations

    def _build_event(
        self,
        *,
        obs: dict[str, Any],
        state: str,
        previous_value: Any,
        current_value: Any,
        correlation_id: str,
        reason: str,
    ) -> dict[str, Any]:
        trigger = obs["trigger"]
        timestamp = str(obs.get("observed_at_utc") or utc_now_iso())
        previous_label = _enum_label(trigger, previous_value)
        current_label = _enum_label(trigger, current_value)
        event_type = _event_type(trigger, state)
        source_id = str(obs.get("source_id") or "") or None
        runtime_asset_id = str(obs.get("runtime_asset_id") or "") or None
        display_name = str(trigger.get("display_name") or trigger.get("signal") or "signal")
        asset_display = str(trigger.get("asset_display") or trigger.get("asset") or "asset")

        if state == "ACTIVE":
            message = (
                f"{source_id or 'gateway'} {asset_display} {display_name} ACTIVE: "
                f"{_format_value(previous_value, previous_label)} -> "
                f"{_format_value(current_value, current_label)}"
            )
        else:
            message = (
                f"{source_id or 'gateway'} {asset_display} {display_name} CLEARED: "
                f"{_format_value(previous_value, previous_label)} -> "
                f"{_format_value(current_value, current_label)}"
            )

        return {
            "event_id": str(uuid4()),
            "correlation_id": correlation_id,
            "timestamp_utc": timestamp,
            "gateway_id": self.config.identity.gateway_id,
            "site_id": self.config.identity.site_id,
            "source_id": source_id,
            "asset_id": runtime_asset_id,
            "signal_name": str(obs.get("signal_name") or trigger.get("signal") or "") or None,
            "event_type": event_type,
            "severity": str(trigger.get("severity") or "Warning"),
            "state": state,
            "previous_value": previous_value,
            "current_value": current_value,
            "message": message,
            "controller_state": None,
            "decision": None,
            "payload": {
                "point_id": trigger.get("point_id"),
                "base_asset_id": trigger.get("asset"),
                "asset_display": trigger.get("asset_display"),
                "display_name": trigger.get("display_name"),
                "address": trigger.get("address"),
                "enumeration_description": trigger.get("enumeration_description"),
                "previous_label": previous_label,
                "current_label": current_label,
                "quality": obs.get("quality"),
                "source_updated_utc": obs.get("source_updated_utc"),
                "sampled_at_utc": obs.get("sampled_at_utc"),
                "snapshot_age_sec": obs.get("snapshot_age_sec"),
                "sample_source": obs.get("sample_source"),
                "primary_telemetry_stream": trigger.get("primary_telemetry_stream"),
                "trigger_reason": reason,
            },
            "dedupe_key": (
                f"{self.config.identity.gateway_id}:"
                f"{source_id or 'gateway'}:"
                f"{trigger.get('asset')}:"
                f"{trigger.get('signal')}"
            ),
            "occurrence_count": 1,
            "cleared_at_utc": timestamp if state == "CLEARED" else None,
        }

    def _priority_for_severity(self, severity: str) -> str:
        sev = severity.strip().lower()
        if sev == "critical":
            return self.producer_config.critical_priority
        if sev == "high":
            return self.producer_config.high_priority
        if sev == "info":
            return self.producer_config.info_priority
        return self.producer_config.warning_priority

    def _load_manifest(self, path: str) -> dict[str, Any]:
        p = Path(path)
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("triggers"), list):
            raise ValueError(f"invalid S4 trigger manifest: {p}")
        return raw

    def _validate_manifest(self) -> None:
        cfg = self.producer_config
        triggers = self._manifest["triggers"]
        if len(self._trigger_by_point_id) != len(triggers):
            raise ValueError("S4 trigger manifest contains duplicate point_id values")
        if cfg.strict_shape:
            if len(triggers) != cfg.expected_canonical_trigger_count:
                raise ValueError(
                    f"S4 expected {cfg.expected_canonical_trigger_count} canonical triggers, got {len(triggers)}"
                )
            runtime_count = sum(int(x.get("runtime_instances") or 0) for x in triggers)
            if runtime_count != cfg.expected_runtime_trigger_count:
                raise ValueError(
                    f"S4 expected {cfg.expected_runtime_trigger_count} runtime triggers, got {runtime_count}"
                )
        for trigger in triggers:
            if not trigger.get("point_id") or not trigger.get("signal") or not trigger.get("asset"):
                raise ValueError("S4 trigger missing point_id/signal/asset")
            if not trigger.get("active_values"):
                raise ValueError(f"S4 trigger has no active_values: {trigger.get('point_id')}")

    def _load_state(self) -> dict[str, dict[str, Any]]:
        p = Path(self.producer_config.state_file)
        if not p.exists():
            return {}
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            signals = raw.get("signals") if isinstance(raw, dict) else None
            return signals if isinstance(signals, dict) else {}
        except Exception as exc:
            log.warning("failed to read S4 lifecycle state; starting clean: %s", exc)
            return {}

    def _save_state(self) -> None:
        safe_write_json(
            self.producer_config.state_file,
            {
                "schema_version": 1,
                "stream": self.producer_config.stream,
                "updated_at_utc": utc_now_iso(),
                "trigger_manifest_sha256": self._manifest.get("source_workbook_sha256"),
                "signals": self._state,
            },
        )

    def status(self) -> dict[str, Any]:
        active_count = sum(1 for state in self._state.values() if state.get("active"))
        return {
            "enabled": self.producer_config.enabled,
            "running": self.running,
            "started_utc": self.started_utc,
            "stream": self.producer_config.stream,
            "poll_interval_sec": self.producer_config.poll_interval_sec,
            "general_snapshot_path": self.producer_config.general_snapshot_path,
            "fast_bess_snapshot_path": self.producer_config.fast_bess_snapshot_path,
            "trigger_manifest_path": self.producer_config.trigger_manifest_path,
            "canonical_trigger_count": len(self._trigger_by_point_id),
            "runtime_trigger_count": int(self._manifest.get("runtime_trigger_count") or 0),
            "tracked_runtime_signal_count": len(self._state),
            "active_runtime_event_count": active_count,
            "startup_emit_active": self.producer_config.startup_emit_active,
            "counters": self.counters.__dict__.copy(),
            "status_generated_utc": utc_now_iso(),
        }

    def _write_status(self) -> None:
        try:
            safe_write_json(self.producer_config.status_file, self.status())
        except Exception as exc:
            log.warning("failed to write S4 producer status: %s", exc)


def _normalize_enum_value(value: Any) -> int | float | str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        rounded = round(float(value))
        if abs(float(value) - rounded) < 1e-9:
            return int(rounded)
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
        rounded = round(number)
        if abs(number - rounded) < 1e-9:
            return int(rounded)
        return number
    except Exception:
        return text


def _enum_label(trigger: dict[str, Any], value: Any) -> str | None:
    normalized = _normalize_enum_value(value)
    if normalized is None:
        return None
    labels = trigger.get("enum_labels") or {}
    return labels.get(str(normalized))


def _event_type(trigger: dict[str, Any], state: str) -> str:
    base = f"{trigger.get('asset')}_{trigger.get('signal')}_{state}"
    return re.sub(r"[^A-Z0-9]+", "_", base.upper()).strip("_")


def _format_value(value: Any, label: str | None) -> str:
    if value is None:
        return "unknown"
    return f"{label} ({value})" if label else str(value)


def _exc_text(exc: Exception) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__
