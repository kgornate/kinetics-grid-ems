from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from nb_ems_gateway.decoding.quality import PointQuality


@dataclass(frozen=True)
class DecodedPointValue:
    point_id: str
    asset_id: str
    normalized_name: str
    address: int
    point_name: str
    entity_name: str
    value: float | None
    unit: str | None
    quality: PointQuality
    timestamp_utc: str
    raw_registers: tuple[int, int] | None = None
    error: str | None = None
    display_name: str | None = None
    category: str | None = None
    dashboard_group: str | None = None
    is_key_signal: bool = False
    enum_map: dict[str, str] | None = None

    @classmethod
    def now(
        cls,
        *,
        point_id: str,
        asset_id: str,
        normalized_name: str,
        address: int,
        point_name: str,
        entity_name: str,
        value: float | None,
        unit: str | None,
        quality: PointQuality,
        raw_registers: tuple[int, int] | None = None,
        error: str | None = None,
        display_name: str | None = None,
        category: str | None = None,
        dashboard_group: str | None = None,
        is_key_signal: bool = False,
        enum_map: dict[str, str] | None = None,
    ) -> "DecodedPointValue":
        return cls(
            point_id=point_id,
            asset_id=asset_id,
            normalized_name=normalized_name,
            address=address,
            point_name=point_name,
            entity_name=entity_name,
            value=value,
            unit=unit,
            quality=quality,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            raw_registers=raw_registers,
            error=error,
            display_name=display_name,
            category=category,
            dashboard_group=dashboard_group,
            is_key_signal=is_key_signal,
            enum_map=enum_map,
        )

    @property
    def enum_text(self) -> str | None:
        if self.value is None or not self.enum_map:
            return None
        try:
            key = str(int(self.value))
        except (TypeError, ValueError):
            key = str(self.value)
        return self.enum_map.get(key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "point_id": self.point_id,
            "asset_id": self.asset_id,
            "normalized_name": self.normalized_name,
            "address": self.address,
            "point_name": self.point_name,
            "entity_name": self.entity_name,
            "display_name": self.display_name or self.point_name,
            "value": self.value,
            "unit": self.unit,
            "enum_text": self.enum_text,
            "quality": self.quality.value,
            "timestamp_utc": self.timestamp_utc,
            "category": self.category,
            "dashboard_group": self.dashboard_group,
            "is_key_signal": self.is_key_signal,
            "raw_registers": list(self.raw_registers) if self.raw_registers else None,
            "error": self.error,
        }


@dataclass(frozen=True)
class PollResult:
    poll_group: str
    values: tuple[DecodedPointValue, ...]
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "poll_group": self.poll_group,
            "values": [value.to_dict() for value in self.values],
            "errors": list(self.errors),
        }
