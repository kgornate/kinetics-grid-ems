from __future__ import annotations

from .outbox import OutboxStore


class SequenceStore:
    """Small facade kept explicit because producers depend on sequence semantics."""

    def __init__(self, outbox: OutboxStore) -> None:
        self.outbox = outbox

    def next(self, stream: str, substream: str | None = None) -> int:
        return self.outbox.next_sequence(stream, substream)

    def current(self, stream: str, substream: str | None = None) -> int:
        return self.outbox.current_sequence(stream, substream)
