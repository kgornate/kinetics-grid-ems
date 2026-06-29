from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Alarm:
    alarm_id: str
    severity: str
    asset_id: str
    message: str
    timestamp_utc: str
    source_signal: str | None = None

    @classmethod
    def create(cls, alarm_id: str, severity: str, asset_id: str, message: str, source_signal: str | None = None) -> "Alarm":
        return cls(
            alarm_id=alarm_id,
            severity=severity,
            asset_id=asset_id,
            message=message,
            source_signal=source_signal,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict:
        return {
            "alarm_id": self.alarm_id,
            "severity": self.severity,
            "asset_id": self.asset_id,
            "message": self.message,
            "source_signal": self.source_signal,
            "timestamp_utc": self.timestamp_utc,
        }
