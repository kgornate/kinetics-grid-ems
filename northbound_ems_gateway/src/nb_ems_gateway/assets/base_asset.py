from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AssetState:
    asset_id: str
    display_name: str
    telemetry: dict[str, Any] = field(default_factory=dict)
    last_update_utc: str | None = None
    online: bool = False

    def update(self, telemetry: dict[str, Any]) -> None:
        self.telemetry.update(telemetry)
        self.last_update_utc = datetime.now(timezone.utc).isoformat()
        self.online = True

    @property
    def signal_count(self) -> int:
        return len(self.telemetry)

    @property
    def good_signal_count(self) -> int:
        return sum(1 for signal in self.telemetry.values() if signal.get("quality") == "good")

    @property
    def bad_signal_count(self) -> int:
        return self.signal_count - self.good_signal_count

    def summary(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "display_name": self.display_name,
            "online": self.online,
            "last_update_utc": self.last_update_utc,
            "signal_count": self.signal_count,
            "good_signal_count": self.good_signal_count,
            "bad_signal_count": self.bad_signal_count,
            "key_signals": self.key_signals(),
        }

    def key_signals(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in self.telemetry.items()
            if bool(value.get("is_key_signal"))
        }

    def categories(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in self.telemetry.values():
            category = value.get("category") or "general"
            counts[category] = counts.get(category, 0) + 1
        return dict(sorted(counts.items()))

    def telemetry_by_category(self, category: str | None = None) -> dict[str, Any]:
        if not category:
            return self.telemetry
        return {
            key: value
            for key, value in self.telemetry.items()
            if (value.get("category") or "general") == category
        }

    def to_dict(self, *, include_telemetry: bool = True, category: str | None = None) -> dict[str, Any]:
        data = self.summary()
        data["categories"] = self.categories()
        if include_telemetry:
            data["telemetry"] = self.telemetry_by_category(category)
        return data
