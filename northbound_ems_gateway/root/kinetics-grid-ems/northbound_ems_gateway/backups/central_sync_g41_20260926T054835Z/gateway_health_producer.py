from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from .config import CentralSyncConfig
from .contracts import make_message, utc_now_iso
from .local_gateway_api import LocalGatewayApiClient
from .outbox import OutboxStore
from .status import safe_write_json

log = logging.getLogger(__name__)


@dataclass
class GatewayHealthProducerCounters:
    poll_count: int = 0
    poll_success_count: int = 0
    poll_failure_count: int = 0
    enqueue_count: int = 0
    heartbeat_count: int = 0
    transition_count: int = 0
    enqueue_failure_count: int = 0
    last_poll_utc: str | None = None
    last_success_utc: str | None = None
    last_enqueue_utc: str | None = None
    last_error: str | None = None
    last_message_id: str | None = None
    last_sequence: int | None = None
    last_reason: str | None = None


class GatewayHealthProducer:
    """Produce S3 gateway_health messages from the existing local /api/health.

    The producer never polls Modbus and never writes a field device. It observes
    the already-running NorthBound Gateway over loopback and persists logical
    messages into the G1 outbox. State transitions are emitted immediately;
    otherwise a heartbeat is emitted at the configured interval.
    """

    def __init__(
        self,
        *,
        config: CentralSyncConfig,
        outbox: OutboxStore,
        api_client: LocalGatewayApiClient | Any | None = None,
    ) -> None:
        self.config = config
        self.producer_config = config.gateway_health
        self.outbox = outbox
        self.api = api_client or LocalGatewayApiClient(config.local_gateway_api)
        self._owns_api = api_client is None
        self.counters = GatewayHealthProducerCounters()
        self.running = False
        self.started_utc = utc_now_iso()
        self._stop = asyncio.Event()
        self._last_state: dict[str, Any] | None = None
        self._last_state_hash: str | None = None
        self._last_emit_monotonic: float | None = None

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
            log.info("gateway health producer disabled")
            return
        self.running = True
        self._stop.clear()
        log.info(
            "gateway health producer started poll=%.1fs heartbeat=%.1fs endpoint=%s",
            self.producer_config.poll_interval_sec,
            self.producer_config.heartbeat_interval_sec,
            self.config.local_gateway_api.health_url,
        )
        try:
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
            log.info("gateway health producer stopped")

    async def collect_once(
        self,
        *,
        force_heartbeat: bool = False,
        reason: str | None = None,
    ) -> dict[str, Any]:
        now_utc = utc_now_iso()
        self.counters.poll_count += 1
        self.counters.last_poll_utc = now_utc

        api_reachable = True
        fetch_error: str | None = None
        try:
            raw_health = await self.api.health()
            self.counters.poll_success_count += 1
            self.counters.last_success_utc = now_utc
            self.counters.last_error = None
        except Exception as exc:
            api_reachable = False
            exc_text = str(exc).strip()
            fetch_error = f"{type(exc).__name__}: {exc_text}" if exc_text else type(exc).__name__
            raw_health = {}
            self.counters.poll_failure_count += 1
            self.counters.last_error = fetch_error
            log.warning("gateway health poll failed: %s", fetch_error)

        health = _normalize_health(raw_health, api_reachable=api_reachable, error=fetch_error)
        state = _transition_state(health)
        state_hash = _stable_hash(state)

        transition = self._last_state_hash is not None and state_hash != self._last_state_hash
        first_observation = self._last_state_hash is None
        heartbeat_due = (
            self._last_emit_monotonic is None
            or (time.monotonic() - self._last_emit_monotonic) >= self.producer_config.heartbeat_interval_sec
        )

        should_emit = force_heartbeat or transition or heartbeat_due
        emitted = False
        message_id: str | None = None
        sequence: int | None = None
        emit_reason = reason
        record_type = "heartbeat"
        changed: dict[str, Any] | None = None

        if transition:
            record_type = "state_transition"
            emit_reason = emit_reason or "state_change"
            changed = _changed_fields(self._last_state or {}, state)
        elif force_heartbeat:
            emit_reason = emit_reason or "manual"
        elif first_observation:
            emit_reason = emit_reason or "initial_observation"
        elif heartbeat_due:
            emit_reason = emit_reason or "interval"

        if should_emit:
            record: dict[str, Any] = {
                "record_type": record_type,
                "reason": emit_reason,
                "observed_at_utc": now_utc,
                "api_reachable": api_reachable,
                "health": health,
            }
            if changed:
                record["transition"] = {"changed": changed}

            sequence = self.outbox.next_sequence(
                self.producer_config.stream,
                self.producer_config.substream,
            )
            priority = (
                self.producer_config.transition_priority
                if record_type == "state_transition"
                else self.producer_config.heartbeat_priority
            )
            message = make_message(
                schema_version=self.config.identity.schema_version,
                gateway_id=self.config.identity.gateway_id,
                site_id=self.config.identity.site_id,
                stream=self.producer_config.stream,
                substream=self.producer_config.substream,
                sequence=sequence,
                priority=priority,
                records=[record],
                created_at_utc=now_utc,
            )
            try:
                inserted = self.outbox.enqueue(message)
            except Exception as exc:
                self.counters.enqueue_failure_count += 1
                self.counters.last_error = f"outbox enqueue failed: {exc}"
                self._write_status()
                raise
            if inserted:
                emitted = True
                message_id = message.message_id
                self.counters.enqueue_count += 1
                self.counters.last_enqueue_utc = now_utc
                self.counters.last_message_id = message_id
                self.counters.last_sequence = sequence
                self.counters.last_reason = emit_reason
                if record_type == "state_transition":
                    self.counters.transition_count += 1
                else:
                    self.counters.heartbeat_count += 1
                self._last_emit_monotonic = time.monotonic()

        self._last_state = state
        self._last_state_hash = state_hash
        self._write_status()

        return {
            "emitted": emitted,
            "message_id": message_id,
            "sequence": sequence,
            "record_type": record_type if emitted else None,
            "reason": emit_reason if emitted else None,
            "api_reachable": api_reachable,
            "state": state,
            "outbox": self.outbox.stats(),
        }

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.producer_config.enabled,
            "running": self.running,
            "started_utc": self.started_utc,
            "stream": self.producer_config.stream,
            "substream": self.producer_config.substream,
            "poll_interval_sec": self.producer_config.poll_interval_sec,
            "heartbeat_interval_sec": self.producer_config.heartbeat_interval_sec,
            "local_health_url": self.config.local_gateway_api.health_url,
            "last_state": self._last_state,
            "counters": self.counters.__dict__.copy(),
            "status_generated_utc": utc_now_iso(),
        }

    def _write_status(self) -> None:
        try:
            safe_write_json(self.producer_config.status_file, self.status())
        except Exception as exc:
            log.warning("failed to write gateway health producer status: %s", exc)


def _normalize_health(raw: dict[str, Any], *, api_reachable: bool, error: str | None) -> dict[str, Any]:
    if not api_reachable:
        return {
            "status": "unreachable",
            "gateway_timestamp_utc": None,
            "gateway_mode": None,
            "source_count": None,
            "online_source_count": 0,
            "asset_count": None,
            "online_asset_count": 0,
            "total_signal_count": None,
            "bad_signal_count": None,
            "commands_enabled": None,
            "control_enabled": None,
            "storage_can_write": None,
            "poll_error_active": True,
            "poll_error_count": None,
            "sources": [],
            "storage": {},
            "fast_bess_logger": {},
            "api_error": error,
        }

    sources_out: list[dict[str, Any]] = []
    raw_sources = raw.get("sources") if isinstance(raw.get("sources"), list) else []
    for src in raw_sources:
        if not isinstance(src, dict):
            continue
        sources_out.append(
            {
                "source_id": src.get("source_id"),
                "online": bool(src.get("online", False)),
                "asset_count": src.get("asset_count"),
                "online_asset_count": src.get("online_asset_count"),
                "signal_count": src.get("signal_count"),
                "bad_signal_count": src.get("bad_signal_count"),
                "last_update_utc": src.get("last_update_utc"),
            }
        )

    storage_raw = raw.get("storage") if isinstance(raw.get("storage"), dict) else {}
    fast_raw = raw.get("fast_bess_logger") if isinstance(raw.get("fast_bess_logger"), dict) else {}
    poll_errors = raw.get("poll_errors") if isinstance(raw.get("poll_errors"), list) else []

    return {
        "status": raw.get("status"),
        "gateway_timestamp_utc": raw.get("timestamp_utc"),
        "gateway_mode": raw.get("gateway_mode"),
        "source_count": raw.get("source_count"),
        "online_source_count": sum(1 for src in sources_out if src["online"]),
        "asset_count": raw.get("asset_count"),
        "online_asset_count": raw.get("online_asset_count"),
        "total_signal_count": raw.get("total_signal_count"),
        "bad_signal_count": raw.get("bad_signal_count"),
        "commands_enabled": raw.get("commands_enabled"),
        "control_enabled": raw.get("control_enabled"),
        "storage_can_write": raw.get("storage_can_write"),
        "poll_error_active": bool(poll_errors),
        "poll_error_count": len(poll_errors),
        "sources": sources_out,
        "storage": {
            "enabled": storage_raw.get("enabled"),
            "mount_ok": storage_raw.get("mount_ok"),
            "can_write": storage_raw.get("can_write"),
            "free_space_mb": storage_raw.get("free_space_mb"),
            "used_percent": storage_raw.get("used_percent"),
            "db_size_mb": storage_raw.get("db_size_mb"),
            "skipped_write_count": storage_raw.get("skipped_write_count"),
            "last_skip_reason": storage_raw.get("last_skip_reason"),
        },
        "fast_bess_logger": {
            "enabled": fast_raw.get("enabled"),
            "running": fast_raw.get("running"),
            "thread_alive": fast_raw.get("thread_alive"),
            "last_sample_utc": fast_raw.get("last_sample_utc"),
            "last_error": fast_raw.get("last_error"),
        },
        "api_error": None,
    }


def _transition_state(health: dict[str, Any]) -> dict[str, Any]:
    # Deliberately excludes continuously changing timestamps, free-space values,
    # and counters so normal telemetry drift does not create event storms.
    return {
        "api_reachable": health.get("status") != "unreachable",
        "status": health.get("status"),
        "online_asset_count": health.get("online_asset_count"),
        "bad_signal_count": health.get("bad_signal_count"),
        "storage_can_write": health.get("storage_can_write"),
        "poll_error_active": health.get("poll_error_active"),
        "fast_bess_logger_running": (health.get("fast_bess_logger") or {}).get("running"),
        "sources": [
            {
                "source_id": s.get("source_id"),
                "online": s.get("online"),
                "online_asset_count": s.get("online_asset_count"),
            }
            for s in (health.get("sources") or [])
            if isinstance(s, dict)
        ],
    }


def _stable_hash(value: dict[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _changed_fields(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    for key in sorted(set(previous) | set(current)):
        if previous.get(key) != current.get(key):
            changed[key] = {"previous": previous.get(key), "current": current.get(key)}
    return changed
