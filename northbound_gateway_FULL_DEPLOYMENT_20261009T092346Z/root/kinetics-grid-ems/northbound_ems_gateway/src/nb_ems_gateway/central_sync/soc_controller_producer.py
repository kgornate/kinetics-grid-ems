from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import CentralSyncConfig
from .contracts import make_message, utc_now_iso
from .local_gateway_api import LocalGatewayApiClient
from .outbox import OutboxCapacityError, OutboxStore
from .status import safe_write_json

log = logging.getLogger(__name__)


@dataclass
class SocControllerProducerCounters:
    poll_count: int = 0
    poll_success_count: int = 0
    poll_failure_count: int = 0
    snapshot_enqueue_count: int = 0
    heartbeat_count: int = 0
    transition_count: int = 0
    event_message_count: int = 0
    event_record_count: int = 0
    history_poll_count: int = 0
    history_poll_failure_count: int = 0
    suppressed_same_state_count: int = 0
    suppressed_duplicate_cycle_error_count: int = 0
    enqueue_failure_count: int = 0
    last_poll_utc: str | None = None
    last_success_utc: str | None = None
    last_enqueue_utc: str | None = None
    last_error: str | None = None
    last_message_id: str | None = None
    last_sequence: int | None = None
    last_reason: str | None = None
    last_event_id: int | None = None


class SocControllerProducer:
    """S5 producer for the v1.2 SOC-controller contract.

    Inputs are strictly the existing loopback controller status/history API.  This
    producer never opens EMS Modbus or the Solis serial port.  It emits a 30-second
    normalized controller heartbeat, immediate semantic state/decision transitions,
    and immediate history events.  Repetitive controller_cycle_error rows are
    fingerprint-deduplicated until the controller becomes healthy again.
    """

    def __init__(
        self,
        *,
        config: CentralSyncConfig,
        outbox: OutboxStore,
        api_client: LocalGatewayApiClient | Any | None = None,
    ) -> None:
        self.config = config
        self.producer_config = config.soc_controller
        self.outbox = outbox
        self.api = api_client or LocalGatewayApiClient(config.local_gateway_api)
        self._owns_api = api_client is None
        self.counters = SocControllerProducerCounters()
        self.running = False
        self.started_utc = utc_now_iso()
        self._stop = asyncio.Event()
        self._last_snapshot_fingerprint: str | None = None
        self._last_emit_monotonic: float | None = None
        self._state = self._load_state()
        if self._state.get("last_snapshot_fingerprint"):
            self._last_snapshot_fingerprint = str(self._state["last_snapshot_fingerprint"])
        self.counters.last_event_id = _as_int(self._state.get("last_event_id"))

    async def close(self) -> None:
        if self._owns_api:
            try:
                await self.api.close()
            except Exception:
                pass

    async def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        if not self.producer_config.enabled:
            log.info("S5 SOC-controller producer disabled")
            return
        self.running = True
        self._stop.clear()
        log.info(
            "S5 SOC-controller producer started poll=%.1fs heartbeat=%.1fs stream=%s",
            self.producer_config.poll_interval_sec,
            self.producer_config.heartbeat_interval_sec,
            self.producer_config.stream,
        )
        try:
            await self._ensure_history_baseline()
            if self.producer_config.startup_emit:
                await self.collect_once(force_heartbeat=True, reason="startup")
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop.wait(),
                        timeout=max(0.2, self.producer_config.poll_interval_sec),
                    )
                    break
                except asyncio.TimeoutError:
                    pass
                await self.collect_once()
        finally:
            self.running = False
            self._write_status()
            log.info("S5 SOC-controller producer stopped")

    async def collect_once(
        self,
        *,
        force_heartbeat: bool = False,
        reason: str | None = None,
    ) -> dict[str, Any]:
        now_utc = utc_now_iso()
        self.counters.poll_count += 1
        self.counters.last_poll_utc = now_utc

        status_error: str | None = None
        raw_status: dict[str, Any] = {}
        try:
            raw_status = await self.api.controller_status()
            self.counters.poll_success_count += 1
            self.counters.last_success_utc = now_utc
            self.counters.last_error = None
        except Exception as exc:
            self.counters.poll_failure_count += 1
            status_error = _exc_text(exc)
            self.counters.last_error = status_error
            log.warning("S5 controller status poll failed: %s", status_error)

        snapshot = _normalize_controller_status(raw_status, api_error=status_error, observed_at_utc=now_utc)
        fingerprint = _stable_hash(_semantic_state(snapshot))
        first_observation = self._last_snapshot_fingerprint is None
        transition = (not first_observation) and fingerprint != self._last_snapshot_fingerprint
        heartbeat_due = (
            self._last_emit_monotonic is None
            or (time.monotonic() - self._last_emit_monotonic) >= self.producer_config.heartbeat_interval_sec
        )
        should_emit_snapshot = force_heartbeat or transition or heartbeat_due

        emitted_snapshot = False
        snapshot_sequence: int | None = None
        emit_reason = reason
        if transition:
            emit_reason = emit_reason or "semantic_state_change"
        elif force_heartbeat:
            emit_reason = emit_reason or "manual"
        elif first_observation:
            emit_reason = emit_reason or "initial_observation"
        elif heartbeat_due:
            emit_reason = emit_reason or "interval"
        else:
            self.counters.suppressed_same_state_count += 1

        if should_emit_snapshot:
            snapshot_sequence = await self._enqueue_records(
                records=[snapshot],
                priority=(
                    self.producer_config.transition_priority
                    if transition
                    else self.producer_config.heartbeat_priority
                ),
                created_at_utc=now_utc,
            )
            if snapshot_sequence is not None:
                emitted_snapshot = True
                self.counters.snapshot_enqueue_count += 1
                if transition:
                    self.counters.transition_count += 1
                else:
                    self.counters.heartbeat_count += 1
                self.counters.last_reason = emit_reason
                self._last_emit_monotonic = time.monotonic()

        # Healthy state clears the repetitive-cycle-error suppression latch.  The
        # same error may then be emitted again if it genuinely reappears later.
        proposed_state = dict(self._state)
        if snapshot.get("healthy") is True:
            proposed_state["last_controller_error_fingerprint"] = None

        event_result = await self._collect_new_events(proposed_state)
        if event_result["state_committed"]:
            proposed_state = event_result["state"]

        self._last_snapshot_fingerprint = fingerprint
        proposed_state["last_snapshot_fingerprint"] = fingerprint
        state_changed = proposed_state != self._state
        self._state = proposed_state
        if state_changed:
            await asyncio.to_thread(self._save_state)
        self.counters.last_event_id = _as_int(self._state.get("last_event_id"))
        self._write_status()

        return {
            "snapshot_emitted": emitted_snapshot,
            "snapshot_sequence": snapshot_sequence,
            "snapshot_reason": emit_reason if emitted_snapshot else None,
            "event_message_emitted": event_result["emitted"],
            "event_count": event_result["event_count"],
            "last_event_id": self.counters.last_event_id,
            "controller_state": (snapshot.get("controller") or {}).get("state"),
            "decision": (snapshot.get("controller") or {}).get("decision"),
            "healthy": snapshot.get("healthy"),
            "outbox": await asyncio.to_thread(self.outbox.stats),
        }

    async def _ensure_history_baseline(self) -> None:
        if _as_int(self._state.get("last_event_id")) is not None:
            return
        try:
            body = await self.api.controller_history(limit=1, offset=0, order="desc")
            items = body.get("items") if isinstance(body.get("items"), list) else []
            latest_id = _as_int(items[0].get("id")) if items else 0
            latest_ts = str(items[0].get("timestamp_utc") or "") if items else ""
            self._state["last_event_id"] = latest_id
            self._state["last_event_timestamp_utc"] = latest_ts or None
            await asyncio.to_thread(self._save_state)
            self.counters.last_event_id = latest_id
            log.info("S5 history cursor baselined at event_id=%s", latest_id)
        except Exception as exc:
            # Do not fail the producer startup just because history is temporarily
            # unavailable.  A later poll will retry without touching control logic.
            self.counters.history_poll_failure_count += 1
            self.counters.last_error = f"history baseline failed: {_exc_text(exc)}"
            log.warning("S5 history baseline failed: %s", exc)

    async def _collect_new_events(self, base_state: dict[str, Any]) -> dict[str, Any]:
        self.counters.history_poll_count += 1
        last_id = _as_int(base_state.get("last_event_id"))
        if last_id is None:
            await self._ensure_history_baseline()
            return {"emitted": False, "event_count": 0, "state_committed": True, "state": dict(self._state)}

        params: dict[str, Any] = {
            "limit": int(self.producer_config.history_poll_limit),
            "offset": 0,
            "order": "asc",
        }
        if base_state.get("last_event_timestamp_utc"):
            params["from_time"] = base_state["last_event_timestamp_utc"]

        try:
            body = await self.api.controller_history(**params)
        except Exception as exc:
            self.counters.history_poll_failure_count += 1
            self.counters.last_error = f"history poll failed: {_exc_text(exc)}"
            return {"emitted": False, "event_count": 0, "state_committed": False, "state": base_state}

        items = body.get("items") if isinstance(body.get("items"), list) else []
        new_items = [item for item in items if isinstance(item, dict) and (_as_int(item.get("id")) or 0) > last_id]
        if not new_items:
            return {"emitted": False, "event_count": 0, "state_committed": True, "state": base_state}

        proposed = dict(base_state)
        output_events: list[dict[str, Any]] = []
        for item in new_items:
            event_id = _as_int(item.get("id")) or last_id
            event_ts = str(item.get("timestamp_utc") or proposed.get("last_event_timestamp_utc") or "")
            include = True
            if str(item.get("event_type") or "") == "controller_cycle_error":
                fp = _stable_hash({
                    "event_type": item.get("event_type"),
                    "device": item.get("device"),
                    "result": item.get("result"),
                    "message": item.get("message"),
                    "payload": item.get("payload") or {},
                })
                if fp == proposed.get("last_controller_error_fingerprint"):
                    include = False
                    self.counters.suppressed_duplicate_cycle_error_count += 1
                else:
                    proposed["last_controller_error_fingerprint"] = fp
            if include:
                output_events.append({"event": _normalize_event(item)})
            proposed["last_event_id"] = event_id
            proposed["last_event_timestamp_utc"] = event_ts or None

        if not output_events:
            return {"emitted": False, "event_count": 0, "state_committed": True, "state": proposed}

        sequence = await self._enqueue_records(
            records=output_events,
            priority=self.producer_config.event_priority,
            created_at_utc=utc_now_iso(),
        )
        if sequence is None:
            return {"emitted": False, "event_count": len(output_events), "state_committed": False, "state": base_state}

        self.counters.event_message_count += 1
        self.counters.event_record_count += len(output_events)
        return {"emitted": True, "event_count": len(output_events), "state_committed": True, "state": proposed}

    async def _enqueue_records(self, *, records: list[dict[str, Any]], priority: str, created_at_utc: str) -> int | None:
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
            log.error("S5 paused by outbox capacity guard: %s", exc)
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
            "heartbeat_interval_sec": self.producer_config.heartbeat_interval_sec,
            "state_file": self.producer_config.state_file,
            "last_semantic_fingerprint": self._last_snapshot_fingerprint,
            "counters": self.counters.__dict__.copy(),
            "status_generated_utc": utc_now_iso(),
        }

    def _load_state(self) -> dict[str, Any]:
        path = Path(self.producer_config.state_file)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as exc:
            log.warning("S5 state load failed; starting with empty cursor: %s", exc)
            return {}

    def _save_state(self) -> None:
        safe_write_json(self.producer_config.state_file, self._state)

    def _write_status(self) -> None:
        try:
            safe_write_json(self.producer_config.status_file, self.status())
        except Exception as exc:
            log.warning("failed to write S5 producer status: %s", exc)


def _normalize_controller_status(raw: dict[str, Any], *, api_error: str | None, observed_at_utc: str) -> dict[str, Any]:
    if api_error:
        return {
            "available": False,
            "timestamp_utc": observed_at_utc,
            "version": None,
            "mode": None,
            "healthy": False,
            "error": api_error,
            "controller": {},
            "thresholds": {},
            "bess": {"X": {}, "Y": {}},
            "solis": {},
            "action_plan": [],
            "last_actions": [],
        }

    controller = raw.get("controller") if isinstance(raw.get("controller"), dict) else {}
    thresholds = raw.get("thresholds") if isinstance(raw.get("thresholds"), dict) else {}
    bess = raw.get("bess") if isinstance(raw.get("bess"), dict) else {}
    solis = raw.get("solis") if isinstance(raw.get("solis"), dict) else {}
    return {
        "available": bool(raw.get("available", False)),
        "timestamp_utc": raw.get("timestamp_utc") or observed_at_utc,
        "version": raw.get("version"),
        "mode": raw.get("mode"),
        "healthy": bool(raw.get("healthy", False)),
        "error": raw.get("error"),
        "controller": {
            "state": controller.get("state"),
            "previous_state": controller.get("previous_state"),
            "decision": controller.get("decision"),
            "solar_off_reason": controller.get("solar_off_reason"),
            "low_cutoff_reason": controller.get("low_cutoff_reason"),
            "trend": dict(controller.get("trend") or {}),
        },
        "thresholds": {
            "derate_soc_percent": thresholds.get("derate_soc_percent"),
            "derate_power_kw": thresholds.get("derate_power_kw"),
            "high_soc_percent": thresholds.get("high_soc_percent"),
            "recovery_soc_percent": thresholds.get("recovery_soc_percent"),
            "low_cutoff_enabled": thresholds.get("low_cutoff_enabled"),
            "low_cutoff_percent": thresholds.get("low_cutoff_percent"),
            "low_recovery_percent": thresholds.get("low_recovery_percent"),
            "settings_revision": thresholds.get("settings_revision"),
            "settings_updated_at_utc": thresholds.get("settings_updated_at_utc"),
            "settings_updated_by": thresholds.get("settings_updated_by"),
        },
        "bess": {
            key: {
                "host": (bess.get(key) or {}).get("host"),
                "soc_percent": (bess.get(key) or {}).get("soc_percent"),
                "online": (bess.get(key) or {}).get("online"),
                "target_state": (bess.get(key) or {}).get("target_state"),
            }
            for key in ("X", "Y")
        },
        "solis": {
            key: solis.get(key)
            for key in (
                "enabled", "online", "state", "target_state", "power_mode", "target_power_kw",
                "active_power_w", "active_power_kw", "power_limit_percent_raw", "power_limit_percent",
                "power_limit_feedback_raw", "power_limit_feedback_percent", "power_limit_equivalent_kw",
                "limited_power_feedback_w", "limiting_status_raw", "serial_port", "unit_id",
            )
        },
        "action_plan": list(raw.get("action_plan") or []),
        "last_actions": list(raw.get("last_actions") or []),
    }


def _semantic_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Fields whose change should trigger immediate S5 snapshot upload.

    Continuously changing SOC/power/trend values are intentionally excluded; they
    ride the 30-second heartbeat.  Immediate command/error detail is carried by the
    history-event path.
    """
    controller = snapshot.get("controller") or {}
    bess = snapshot.get("bess") or {}
    solis = snapshot.get("solis") or {}
    return {
        "available": snapshot.get("available"),
        "healthy": snapshot.get("healthy"),
        "error": snapshot.get("error"),
        "version": snapshot.get("version"),
        "mode": snapshot.get("mode"),
        "controller": {
            "state": controller.get("state"),
            "decision": controller.get("decision"),
            "solar_off_reason": controller.get("solar_off_reason"),
            "low_cutoff_reason": controller.get("low_cutoff_reason"),
        },
        "thresholds": snapshot.get("thresholds") or {},
        "bess": {
            key: {
                "online": (bess.get(key) or {}).get("online"),
                "target_state": (bess.get(key) or {}).get("target_state"),
            }
            for key in ("X", "Y")
        },
        "solis": {
            key: solis.get(key)
            for key in (
                "enabled", "online", "state", "target_state", "power_mode", "target_power_kw",
                "power_limit_percent_raw", "power_limit_feedback_raw", "limiting_status_raw",
            )
        },
        "action_plan": snapshot.get("action_plan") or [],
        "last_actions": snapshot.get("last_actions") or [],
    }


def _normalize_event(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _as_int(item.get("id")),
        "timestamp_utc": item.get("timestamp_utc"),
        "severity": item.get("severity"),
        "event_type": item.get("event_type"),
        "device": item.get("device"),
        "controller_state": item.get("controller_state"),
        "decision": item.get("decision"),
        "soc_x": item.get("soc_x"),
        "soc_y": item.get("soc_y"),
        "solis_state": item.get("solis_state"),
        "solis_power_w": item.get("solis_power_w"),
        "target": item.get("target"),
        "result": item.get("result"),
        "message": item.get("message"),
        "payload": item.get("payload") if isinstance(item.get("payload"), dict) else {},
    }


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def _exc_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__
