from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .status import utc_now_iso


class TransportPauseController:
    """File-backed live transport pause control.

    Presence of the pause file means *transport only* is paused. Producers,
    outbox persistence, overflow archival and all local gateway services remain
    active. The file is deliberately external to the source tree so the state
    survives a Central Sync process restart.
    """

    def __init__(self, pause_file: str) -> None:
        self.path = Path(pause_file)

    def is_paused(self) -> bool:
        return self.path.exists()

    def read_metadata(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            raw = self.path.read_text(encoding="utf-8").strip()
            if not raw:
                return {}
            value = json.loads(raw)
            return value if isinstance(value, dict) else {"raw": value}
        except Exception:
            return {"raw": "unreadable"}

    def status(self) -> dict[str, Any]:
        metadata = self.read_metadata()
        return {
            "paused": self.is_paused(),
            "pause_file": str(self.path),
            "metadata": metadata,
            "status_generated_utc": utc_now_iso(),
        }
