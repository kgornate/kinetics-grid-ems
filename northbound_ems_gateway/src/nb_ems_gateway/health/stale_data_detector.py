from __future__ import annotations

from datetime import datetime, timezone


def is_stale(timestamp_utc: str | None, max_age_sec: float) -> bool:
    if not timestamp_utc:
        return True
    ts = datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    return age > max_age_sec
