"""Event storage facade."""

from __future__ import annotations

from typing import Any, Dict, Optional


class EventStore:
    """Write event rows through the active storage backend."""

    def __init__(self, backend: Any):
        self.backend = backend
        self.last_write_ok: Optional[bool] = None
        self.last_error: Optional[str] = None

    def log(self, *args: Any, **kwargs: Any) -> bool:
        try:
            result = bool(self.backend.log_event(*args, **kwargs))
            self.last_write_ok = result
            if result:
                self.last_error = None
            return result
        except Exception as error:
            self.last_write_ok = False
            self.last_error = str(error)
            raise

    write = log
    append = log

    def get_status(self) -> Dict[str, Any]:
        return {
            "store_type": "event",
            "last_write_ok": self.last_write_ok,
            "last_error": self.last_error,
        }
