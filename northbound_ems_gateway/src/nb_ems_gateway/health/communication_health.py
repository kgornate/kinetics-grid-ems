from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class CommunicationHealth:
    connected: bool = False
    last_success_utc: str | None = None
    last_error: str | None = None

    def mark_success(self) -> None:
        self.connected = True
        self.last_success_utc = datetime.now(timezone.utc).isoformat()
        self.last_error = None

    def mark_error(self, error: str) -> None:
        self.connected = False
        self.last_error = error

    def to_dict(self) -> dict:
        return {
            "connected": self.connected,
            "last_success_utc": self.last_success_utc,
            "last_error": self.last_error,
        }
