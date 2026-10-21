from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .config import CentralSyncConfig
from .contracts import utc_now_iso
from .outbox import OutboxStore
from .producer_common import ProducerCounters, ProducerLoopMixin, emit_message


class CompatibilityApplicationProducer(ProducerLoopMixin):
    """Optional S5/S6/S7 slot preserving the frozen Northbound stream names.

    Kalpa does not enable these applications by default. When a compatible
    application writes a JSON object to source_path, it can be forwarded without
    changing the backend stream architecture.
    """
    def __init__(self, *, config: CentralSyncConfig, outbox: OutboxStore, producer_config: Any) -> None:
        self.config=config; self.producer_config=producer_config; self.outbox=outbox
        self.counters=ProducerCounters(); self.running=False; self.started_utc=utc_now_iso(); self._stop=asyncio.Event()
        self._last_raw: str | None=None

    async def collect_once(self, *, force_emit: bool=False) -> dict[str,Any]:
        self.counters.poll_count += 1; self.counters.last_poll_utc=utc_now_iso()
        if not self.producer_config.source_path:
            return {"emitted":False,"reason":"source_path_not_configured"}
        p=Path(self.producer_config.source_path)
        if not p.exists(): return {"emitted":False,"reason":"source_missing"}
        raw=await asyncio.to_thread(p.read_text, encoding='utf-8')
        if not force_emit and raw==self._last_raw: return {"emitted":False,"reason":"duplicate"}
        payload=json.loads(raw)
        records=payload if isinstance(payload,list) else [payload]
        records=[x for x in records if isinstance(x,dict)]
        if not records: return {"emitted":False,"reason":"empty"}
        inserted,msg=await asyncio.to_thread(emit_message,config=self.config,outbox=self.outbox,stream=self.producer_config.stream,substream=self.producer_config.substream,priority=self.producer_config.priority,records=records,created_at_utc=utc_now_iso())
        self._last_raw=raw; self.counters.success_count += 1; self.counters.last_success_utc=utc_now_iso()
        if inserted:
            self.counters.message_count += 1; self.counters.record_count += len(records); self.counters.last_enqueue_utc=utc_now_iso(); self.counters.last_message_id=msg.message_id; self.counters.last_sequence=msg.sequence
        self._write_status(); return {"emitted":bool(inserted),"record_count":len(records)}
