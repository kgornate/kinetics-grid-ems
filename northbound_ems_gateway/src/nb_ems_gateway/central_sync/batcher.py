from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from .contracts import TransportBatch
from .outbox import OutboxItem, OutboxStore


@dataclass(frozen=True)
class PreparedBatch:
    request_id: str
    body: dict[str, Any]
    items: list[OutboxItem]
    json_bytes: bytes

    @property
    def message_ids(self) -> list[str]:
        return [item.message_id for item in self.items]


class OutboxBatcher:
    def __init__(
        self,
        outbox: OutboxStore,
        *,
        gateway_id: str,
        coalescing_window_sec: float,
        max_messages: int,
        max_bytes: int,
    ) -> None:
        self.outbox = outbox
        self.gateway_id = gateway_id
        self.coalescing_window_sec = coalescing_window_sec
        self.max_messages = max_messages
        self.max_bytes = max_bytes

    def prepare(self) -> PreparedBatch | None:
        items = self.outbox.eligible(
            now_epoch=time.time(),
            coalescing_window_sec=self.coalescing_window_sec,
            max_messages=self.max_messages,
            max_bytes=self.max_bytes,
        )
        if not items:
            return None
        messages = [item.payload() for item in items]
        batch = TransportBatch(gateway_id=self.gateway_id, messages=messages)
        body = batch.model_dump(mode="json")
        raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return PreparedBatch(request_id=batch.request_id, body=body, items=items, json_bytes=raw)
