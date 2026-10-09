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
from .local_gateway_api import LocalGatewayApiClient
from .outbox import OutboxCapacityError, OutboxStore
from .status import safe_write_json

log = logging.getLogger(__name__)


@dataclass
class SolisProducerCounters:
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
    enqueue_failure_count: int = 0
    last_poll_utc: str | None = None
    last_success_utc: str | None = None
    last_enqueue_utc: str | None = None
    last_error: str | None = None
    last_message_id: str | None = None
    last_sequence: int | None = None
    last_reason: str | None = None
    last_event_id: int | None = None
    last_command_event_id: int | None = None
    last_command_verified: bool | None = None


class SolisProducer:
    """S6 producer for the v1.2 Solis operational/event contract.

    The producer consumes only the existing loopback ``/api/solis/status`` and
    ``/api/solis/history`` views.  It never opens the Solis serial port and never
    performs an extra Modbus RTU read.  Operational telemetry is emitted every five
    seconds, semantic state/communication/power-limit changes are emitted on the
    next one-second status poll, and Solis history events are forwarded once using
    a persistent event-id cursor.
    """

    def __init__(
        self,
        *,
        config: CentralSyncConfig,
        outbox: OutboxStore,
        api_client: LocalGatewayApiClient | Any | None = None,
    ) -> None:
        self.config = config
        self.producer_config = config.solis
        self.outbox = outbox
        self.api = api_client or LocalGatewayApiClient(config.local_gateway_api)
        self._owns_api = api_client is None
        self.counters = SolisProducerCounters()
        self.running = False
        self.started_utc = utc_now_iso()
        self._stop = asyncio.Event()
        self._state = self._load_state()
        self._last_snapshot_fingerprint: str | None = (
            str(self._state.get("last_snapshot_fingerprint"))
            if self._state.get("last_snapshot_fingerprint")
            else None
        )
        self._last_emit_monotonic: float | None = None
        self._last_history_poll_monotonic: float | None = None
        self.counters.last_event_id = _as_int(self._state.get("last_event_id"))
        self.counters.last_command_event_id = _as_int(self._state.get("last_command_event_id"))
        if "last_command_verified" in self._state:
            value = self._state.get("last_command_verified")
            self.counters.last_command_verified = value if isinstance(value, bool) else None

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
            log.info("S6 Solis producer disabled")
            return
        self.running = True
        self._stop.clear()
        log.info(
            "S6 Solis producer started poll=%.1fs heartbeat=%.1fs history=%.1fs stream=%s",
            self.producer_config.poll_interval_sec,
            self.producer_config.heartbeat_interval_sec,
            self.producer_config.history_poll_interval_sec,
            self.producer_config.stream,
        )
        try:
            await self._ensure_history_baseline()
            if self.producer_config.startup_emit:
                await self.collect_once(force_heartbeat=True, force_history=True, reason="startup")
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
            log.info("S6 Solis producer stopped")

    async def collect_once(
        self,
        *,
        force_heartbeat: bool = False,
        force_history: bool = False,
        reason: str | None = None,
    ) -> dict[str, Any]:
        now_utc = utc_now_iso()
        self.counters.poll_count += 1
        self.counters.last_poll_utc = now_utc

        raw_status: dict[str, Any] = {}
        api_error: str | None = None
        try:
            raw_status = await self.api.solis_status()
            self.counters.poll_success_count += 1
            self.counters.last_success_utc = now_utc
            self.counters.last_error = None
        except Exception as exc:
            self.counters.poll_failure_count += 1
            api_error = _exc_text(exc)
            self.counters.last_error = api_error
            log.warning("S6 Solis status poll failed: %s", api_error)

        proposed_state = dict(self._state)
        _update_last_good_read(proposed_state, raw_status, observed_at_utc=now_utc)

        history_due = force_history or self._history_due()
        event_result = {
            "emitted": False,
            "event_count": 0,
            "state_committed": True,
            "state": proposed_state,
        }
        if history_due:
            event_result = await self._collect_new_events(proposed_state)
            self._last_history_poll_monotonic = time.monotonic()
            if event_result["state_committed"]:
                proposed_state = event_result["state"]

        snapshot = _normalize_solis_status(
            raw_status,
            api_error=api_error,
            observed_at_utc=now_utc,
            state=proposed_state,
            stale_after_sec=self.producer_config.stale_after_sec,
        )
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

        self._last_snapshot_fingerprint = fingerprint
        proposed_state["last_snapshot_fingerprint"] = fingerprint
        state_changed = proposed_state != self._state
        self._state = proposed_state
        if state_changed:
            await asyncio.to_thread(self._save_state)

        self.counters.last_event_id = _as_int(self._state.get("last_event_id"))
        self.counters.last_command_event_id = _as_int(self._state.get("last_command_event_id"))
        value = self._state.get("last_command_verified")
        self.counters.last_command_verified = value if isinstance(value, bool) else None
        self._write_status()

        solis = snapshot.get("solis") or {}
        return {
            "snapshot_emitted": emitted_snapshot,
            "snapshot_sequence": snapshot_sequence,
            "snapshot_reason": emit_reason if emitted_snapshot else None,
            "event_message_emitted": event_result["emitted"],
            "event_count": event_result["event_count"],
            "last_event_id": self.counters.last_event_id,
            "online": solis.get("online"),
            "state": solis.get("state"),
            "power_mode": solis.get("power_mode"),
            "communication_quality": solis.get("communication_quality"),
            "last_successful_read_utc": solis.get("last_successful_read_utc"),
            "outbox": await asyncio.to_thread(self.outbox.stats),
        }

    def _history_due(self) -> bool:
        if self._last_history_poll_monotonic is None:
            return True
        return (
            time.monotonic() - self._last_history_poll_monotonic
        ) >= self.producer_config.history_poll_interval_sec

    async def _ensure_history_baseline(self) -> None:
        if _as_int(self._state.get("last_event_id")) is not None:
            return
        try:
            body = await self.api.solis_history(limit=1, offset=0, order="desc")
            items = body.get("items") if isinstance(body.get("items"), list) else []
            latest = items[0] if items and isinstance(items[0], dict) else {}
            latest_id = _as_int(latest.get("id")) or 0
            latest_ts = str(latest.get("timestamp_utc") or "")
            self._state["last_event_id"] = latest_id
            self._state["last_event_timestamp_utc"] = latest_ts or None

            # Initialize command verification without replaying the old command.
            cmd_body = await self.api.solis_history(
                event_type="solis_command",
                limit=1,
                offset=0,
                order="desc",
            )
            cmd_items = cmd_body.get("items") if isinstance(cmd_body.get("items"), list) else []
            cmd = cmd_items[0] if cmd_items and isinstance(cmd_items[0], dict) else {}
            if cmd:
                cmd_id = _as_int(cmd.get("id"))
                self._state["last_command_event_id"] = cmd_id
                self._state["last_command_verified"] = _command_verified(cmd)
                self._state["last_command_target"] = cmd.get("target")
                self._state["last_command_timestamp_utc"] = cmd.get("timestamp_utc")

            await asyncio.to_thread(self._save_state)
            self.counters.last_event_id = latest_id
            log.info("S6 history cursor baselined at event_id=%s", latest_id)
        except Exception as exc:
            self.counters.history_poll_failure_count += 1
            self.counters.last_error = f"history baseline failed: {_exc_text(exc)}"
            log.warning("S6 history baseline failed: %s", exc)

    async def _collect_new_events(self, base_state: dict[str, Any]) -> dict[str, Any]:
        self.counters.history_poll_count += 1
        last_id = _as_int(base_state.get("last_event_id"))
        if last_id is None:
            await self._ensure_history_baseline()
            return {
                "emitted": False,
                "event_count": 0,
                "state_committed": True,
                "state": dict(self._state),
            }

        params: dict[str, Any] = {
            "limit": int(self.producer_config.history_poll_limit),
            "offset": 0,
            "order": "asc",
        }
        if base_state.get("last_event_timestamp_utc"):
            params["from_time"] = base_state["last_event_timestamp_utc"]

        try:
            body = await self.api.solis_history(**params)
        except Exception as exc:
            self.counters.history_poll_failure_count += 1
            self.counters.last_error = f"history poll failed: {_exc_text(exc)}"
            return {
                "emitted": False,
                "event_count": 0,
                "state_committed": False,
                "state": base_state,
            }

        items = body.get("items") if isinstance(body.get("items"), list) else []
        new_items = [
            item
            for item in items
            if isinstance(item, dict) and (_as_int(item.get("id")) or 0) > last_id
        ]
        if not new_items:
            return {
                "emitted": False,
                "event_count": 0,
                "state_committed": True,
                "state": base_state,
            }

        proposed = dict(base_state)
        output_events: list[dict[str, Any]] = []
        for item in new_items:
            event_id = _as_int(item.get("id")) or last_id
            event_ts = str(item.get("timestamp_utc") or proposed.get("last_event_timestamp_utc") or "")
            output_events.append({"event": _normalize_event(item)})
            proposed["last_event_id"] = event_id
            proposed["last_event_timestamp_utc"] = event_ts or None
            if str(item.get("event_type") or "") == "solis_command":
                proposed["last_command_event_id"] = event_id
                proposed["last_command_verified"] = _command_verified(item)
                proposed["last_command_target"] = item.get("target")
                proposed["last_command_timestamp_utc"] = item.get("timestamp_utc")

        sequence = await self._enqueue_records(
            records=output_events,
            priority=self.producer_config.event_priority,
            created_at_utc=utc_now_iso(),
        )
        if sequence is None:
            return {
                "emitted": False,
                "event_count": len(output_events),
                "state_committed": False,
                "state": base_state,
            }

        self.counters.event_message_count += 1
        self.counters.event_record_count += len(output_events)
        return {
            "emitted": True,
            "event_count": len(output_events),
            "state_committed": True,
            "state": proposed,
        }

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
            log.error("S6 paused by outbox capacity guard: %s", exc)
            return None
        except Exception as exc:
            self.counters.enqueue_failure_count += 1
            self.counters.last_error = f"outbox enqueue failed: {_exc_text(exc)}"
            log.exception("S6 enqueue failed")
            return None
        if not inserted:
            self.counters.enqueue_failure_count += 1
            self.counters.last_error = "outbox enqueue returned false"
            return None
        self.counters.last_enqueue_utc = created_at_utc
        self.counters.last_message_id = message.message_id
        self.counters.last_sequence = sequence
        log.info(
            "S6 message enqueued sequence=%s records=%s priority=%s",
            sequence,
            len(records),
            priority,
        )
        return sequence

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.producer_config.enabled),
            "running": bool(self.running),
            "stream": self.producer_config.stream,
            "substream": self.producer_config.substream,
            "poll_interval_sec": self.producer_config.poll_interval_sec,
            "heartbeat_interval_sec": self.producer_config.heartbeat_interval_sec,
            "history_poll_interval_sec": self.producer_config.history_poll_interval_sec,
            "stale_after_sec": self.producer_config.stale_after_sec,
            "state_file": self.producer_config.state_file,
            "status_file": self.producer_config.status_file,
            "started_utc": self.started_utc,
            "last_successful_read_utc": self._state.get("last_successful_read_utc"),
            "last_command_verified": self._state.get("last_command_verified"),
            "last_command_event_id": self._state.get("last_command_event_id"),
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
            log.warning("S6 state load failed; starting with empty cursor: %s", exc)
            return {}

    def _save_state(self) -> None:
        safe_write_json(self.producer_config.state_file, self._state)

    def _write_status(self) -> None:
        try:
            safe_write_json(self.producer_config.status_file, self.status())
        except Exception as exc:
            log.warning("failed to write S6 producer status: %s", exc)


def _update_last_good_read(state: dict[str, Any], raw: dict[str, Any], *, observed_at_utc: str) -> None:
    solis = raw.get("solis") if isinstance(raw.get("solis"), dict) else {}
    if raw.get("available") is True and solis.get("online") is True:
        ts = str(raw.get("timestamp_utc") or observed_at_utc)
        state["last_successful_read_utc"] = ts


def _normalize_solis_status(
    raw: dict[str, Any],
    *,
    api_error: str | None,
    observed_at_utc: str,
    state: dict[str, Any],
    stale_after_sec: float,
) -> dict[str, Any]:
    solis_raw = raw.get("solis") if isinstance(raw.get("solis"), dict) else {}
    available = bool(raw.get("available", False)) if not api_error else False
    last_good = state.get("last_successful_read_utc")
    age = _age_sec(last_good, observed_at_utc)

    online = solis_raw.get("online") if available else None
    if api_error:
        quality = "ERROR"
    elif not available:
        quality = "ERROR"
    elif online is not True:
        quality = "OFFLINE"
    elif age is None or age > float(stale_after_sec):
        quality = "STALE"
    else:
        quality = "GOOD"

    command_verified = solis_raw.get("command_verified")
    if not isinstance(command_verified, bool):
        value = state.get("last_command_verified")
        command_verified = value if isinstance(value, bool) else None

    command_id = solis_raw.get("command_id")
    if command_id is not None:
        command_id = str(command_id)

    return {
        "available": available,
        "timestamp_utc": raw.get("timestamp_utc") or observed_at_utc,
        "controller_state": raw.get("controller_state"),
        "decision": raw.get("decision"),
        "solis": {
            "enabled": solis_raw.get("enabled"),
            "online": online,
            "state": solis_raw.get("state"),
            "target_state": solis_raw.get("target_state"),
            "power_mode": solis_raw.get("power_mode"),
            "target_power_kw": solis_raw.get("target_power_kw"),
            "active_power_w": solis_raw.get("active_power_w"),
            "active_power_kw": solis_raw.get("active_power_kw"),
            "power_limit_percent_raw": solis_raw.get("power_limit_percent_raw"),
            "power_limit_percent": solis_raw.get("power_limit_percent"),
            "power_limit_feedback_raw": solis_raw.get("power_limit_feedback_raw"),
            "power_limit_feedback_percent": solis_raw.get("power_limit_feedback_percent"),
            "power_limit_equivalent_kw": solis_raw.get("power_limit_equivalent_kw"),
            "limited_power_feedback_w": solis_raw.get("limited_power_feedback_w"),
            "limiting_status_raw": solis_raw.get("limiting_status_raw"),
            "serial_port": solis_raw.get("serial_port"),
            "unit_id": solis_raw.get("unit_id"),
            "last_successful_read_utc": last_good,
            "last_read_age_sec": age,
            # v1.14 does not currently expose these two fields.  Preserve the
            # contract and automatically pass them through when the controller API
            # gains a source; never synthesize a Modbus exception/error value.
            "last_exception_code": solis_raw.get("last_exception_code"),
            "last_error": solis_raw.get("last_error"),
            "communication_quality": quality,
            "command_verified": command_verified,
            # Reserved for future D1/S9 correlation.  Pass through only if a real
            # controller/API source appears; do not manufacture a command id.
            "command_id": command_id,
        },
    }


def _semantic_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    solis = snapshot.get("solis") or {}
    return {
        "available": snapshot.get("available"),
        "solis": {
            key: solis.get(key)
            for key in (
                "enabled",
                "online",
                "state",
                "target_state",
                "power_mode",
                "target_power_kw",
                "power_limit_percent_raw",
                "power_limit_percent",
                "power_limit_feedback_raw",
                "power_limit_feedback_percent",
                "power_limit_equivalent_kw",
                "limited_power_feedback_w",
                "limiting_status_raw",
                "serial_port",
                "unit_id",
                "last_exception_code",
                "last_error",
                "communication_quality",
                "command_verified",
                "command_id",
            )
        },
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


def _command_verified(item: dict[str, Any]) -> bool | None:
    result = str(item.get("result") or "").lower()
    if result == "success":
        return True
    if result == "failed":
        return False
    return None


def _age_sec(then_utc: Any, now_utc: str) -> float | None:
    if not then_utc:
        return None
    try:
        then = _parse_utc(str(then_utc))
        now = _parse_utc(now_utc)
        return round(max(0.0, (now - then).total_seconds()), 3)
    except Exception:
        return None


def _parse_utc(value: str) -> datetime:
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


def _exc_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__
