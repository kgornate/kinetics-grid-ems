from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .config import CentralSyncConfig
from .contracts import utc_now_iso
from .local_gateway_api import LocalGatewayApiClient
from .outbox import OutboxStore
from .producer_common import ProducerCounters, ProducerLoopMixin, emit_message
from .status import safe_write_json


class AlarmEventProducer(ProducerLoopMixin):
    """S4 adapter for the gateway's durable alarm_history table.

    First startup establishes a cursor by default so installing Central Sync on
    an existing gateway never floods the backend with old history.
    """

    def __init__(self, *, config: CentralSyncConfig, outbox: OutboxStore, local_api: Any | None = None) -> None:
        self.config = config
        self.producer_config = config.alarms_events
        self.outbox = outbox
        self.local_api = local_api or LocalGatewayApiClient(config.local_gateway_api)
        self._owns_api = local_api is None
        self.counters = ProducerCounters()
        self.running = False
        self.started_utc = utc_now_iso()
        self._stop = asyncio.Event()
        self._state_path = Path(self.producer_config.state_file)
        self._state = self._load_state()

    async def close(self) -> None:
        if self._owns_api:
            await self.local_api.close()

    def _load_state(self) -> dict[str, Any]:
        try:
            if self._state_path.exists():
                value = json.loads(self._state_path.read_text(encoding="utf-8"))
                if isinstance(value, dict): return value
        except Exception:
            pass
        return {"initialized": False, "last_timestamp": None, "seen_ids": []}

    def _save_state(self) -> None:
        safe_write_json(str(self._state_path), self._state)

    @staticmethod
    def _event_id(item: dict[str, Any]) -> str:
        raw = "|".join(str(item.get(k) or "") for k in ("timestamp", "alarm_key", "asset_id", "action", "code"))
        return str(uuid5(NAMESPACE_URL, "ornate-alarm:" + raw))

    async def collect_once(self) -> dict[str, Any]:
        self.counters.poll_count += 1
        self.counters.last_poll_utc = utc_now_iso()
        params: dict[str, Any] = {"limit": 5000}
        if self._state.get("last_timestamp"):
            params["since"] = self._state["last_timestamp"]
        body = await self.local_api.alarms_history(**params)
        history = body.get("history", []) if isinstance(body, dict) else []
        if not isinstance(history, list): history = []
        history = sorted((x for x in history if isinstance(x, dict)), key=lambda x: str(x.get("timestamp") or ""))

        if not self._state.get("initialized") and not self.producer_config.startup_emit_existing:
            if history:
                newest = str(history[-1].get("timestamp") or "")
                ids = [self._event_id(x) for x in history if str(x.get("timestamp") or "") == newest]
                self._state = {"initialized": True, "last_timestamp": newest, "seen_ids": ids[-100:]}
            else:
                self._state["initialized"] = True
            self._save_state()
            self.counters.success_count += 1
            self.counters.last_success_utc = utc_now_iso()
            self._write_status()
            return {"emitted": False, "reason": "baseline_established", "baseline_count": len(history)}

        seen = set(self._state.get("seen_ids") or [])
        new_items = [x for x in history if self._event_id(x) not in seen]
        if not new_items:
            self.counters.success_count += 1
            self.counters.last_success_utc = utc_now_iso()
            self._write_status()
            return {"emitted": False, "reason": "no_new_events"}

        records: list[dict[str, Any]] = []
        for item in new_items:
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            event_id = self._event_id(item)
            action = str(item.get("action") or "raised")
            timestamp = str(item.get("timestamp") or utc_now_iso())
            record = {
                "event_id": event_id,
                "correlation_id": payload.get("correlation_id"),
                "timestamp_utc": timestamp,
                "gateway_id": self.config.identity.gateway_id,
                "site_id": self.config.identity.site_id,
                "source_id": payload.get("source_id") or "gateway_alarm_engine",
                "asset_id": item.get("asset_id"),
                "signal_name": payload.get("signal_name") or item.get("code") or item.get("alarm_key"),
                "event_type": payload.get("event_type") or "alarm",
                "severity": item.get("severity") or payload.get("severity") or "warning",
                "state": "active" if action == "raised" else "cleared",
                "previous_value": payload.get("previous_value"),
                "current_value": payload.get("current_value"),
                "message": payload.get("message") or payload.get("description") or str(item.get("alarm_key") or "alarm"),
                "controller_state": payload.get("controller_state"),
                "decision": payload.get("decision"),
                "payload": payload,
                "dedupe_key": str(item.get("alarm_key") or event_id),
                "occurrence_count": int(payload.get("occurrence_count") or 1),
                "cleared_at_utc": timestamp if action == "cleared" else None,
            }
            records.append(record)

        inserted, msg = await asyncio.to_thread(
            emit_message,
            config=self.config, outbox=self.outbox,
            stream=self.producer_config.stream, substream=self.producer_config.substream,
            priority=self.producer_config.priority, records=records,
            created_at_utc=records[-1]["timestamp_utc"],
        )
        newest = str(new_items[-1].get("timestamp") or "")
        newest_ids = [self._event_id(x) for x in history if str(x.get("timestamp") or "") == newest]
        self._state = {"initialized": True, "last_timestamp": newest, "seen_ids": newest_ids[-100:]}
        self._save_state()
        self.counters.success_count += 1
        self.counters.last_success_utc = utc_now_iso()
        if inserted:
            self.counters.message_count += 1
            self.counters.record_count += len(records)
            self.counters.last_enqueue_utc = utc_now_iso()
            self.counters.last_message_id = msg.message_id
            self.counters.last_sequence = msg.sequence
        self.counters.last_error = None
        self._write_status()
        return {"emitted": bool(inserted), "record_count": len(records), "message_id": msg.message_id if msg else None}
