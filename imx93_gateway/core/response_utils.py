"""Small response helpers shared by future gateway modules."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional


JsonDict = Dict[str, Any]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def command_response(
    *,
    request_id: Optional[Any],
    command: str,
    status: str,
    message: str,
    data: Optional[JsonDict] = None,
) -> JsonDict:
    return {
        "type": "response",
        "request_id": request_id,
        "timestamp": now_iso(),
        "status": status,
        "command": command,
        "message": message,
        "data": data or {},
    }
