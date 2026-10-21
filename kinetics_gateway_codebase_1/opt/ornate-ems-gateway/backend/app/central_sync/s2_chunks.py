"""S2 logical message splitting; bound is serialized JSON envelope size."""
from __future__ import annotations

import json
from typing import Any

MAX_S2_MESSAGE_BYTES = 96 * 1024

class S2RecordTooLarge(ValueError):
    pass


def json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def split_s2_records(records: list[dict[str, Any]], *, overhead_allowance: int = 1024,
                     max_message_bytes: int = MAX_S2_MESSAGE_BYTES) -> list[list[dict[str, Any]]]:
    """Conservative O(n) packing; exact envelope bound is enforced at INSERT."""
    if max_message_bytes < 4096:
        raise ValueError("S2 bound must be at least 4096 bytes")
    limit = max_message_bytes - overhead_allowance
    chunks: list[list[dict[str, Any]]] = []
    chunk: list[dict[str, Any]] = []
    size = 0
    for record in records:
        encoded_size = len(json_bytes(record))
        # includes comma between adjacent records; allowance reserves metadata.
        if encoded_size + 2 > limit:
            raise S2RecordTooLarge(f"one S2 signal exceeds {max_message_bytes} byte logical envelope: {record.get('runtime_signal_id')}")
        if chunk and size + 1 + encoded_size > limit:
            chunks.append(chunk)
            chunk = []
            size = 0
        chunk.append(record)
        size += encoded_size + (1 if len(chunk) > 1 else 0)
    if chunk:
        chunks.append(chunk)
    return chunks
