from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ProtocolCatalog:
    metadata: dict[str, Any]
    points: tuple[dict[str, Any], ...]
    reserved_ranges: tuple[dict[str, Any], ...] = ()

    @classmethod
    def load(cls, path: str | Path) -> "ProtocolCatalog":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            metadata=payload.get("metadata", {}),
            points=tuple(payload.get("points", [])),
            reserved_ranges=tuple(payload.get("reserved_ranges", [])),
        )

    def select(
        self,
        *,
        scope: str | None = None,
        category: str | None = None,
        poll_classes: set[str] | None = None,
        writable: bool | None = None,
        include_reserved: bool = False,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for point in self.points:
            if scope and point.get("scope") != scope:
                continue
            if category and point.get("category") != category:
                continue
            if poll_classes and point.get("poll_class") not in poll_classes:
                continue
            if not include_reserved and point.get("reserved"):
                continue
            if writable is not None:
                is_writable = "W" in str(point.get("access", "R")).upper()
                if is_writable != writable:
                    continue
            result.append(point)
        return result

    def by_key(self, key: str, *, scope: str | None = None) -> dict[str, Any] | None:
        normalized = key.strip().lower()
        for point in self.points:
            if scope and point.get("scope") != scope:
                continue
            if str(point.get("key", "")).lower() == normalized or str(point.get("id", "")).lower() == normalized:
                return point
        return None

    def by_address(self, address: int) -> list[dict[str, Any]]:
        return [point for point in self.points if int(point.get("address", -1)) == address]

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        writable = 0
        for point in self.points:
            group = f"{point.get('scope')}.{point.get('category')}"
            counts[group] = counts.get(group, 0) + 1
            if "W" in str(point.get("access", "R")).upper():
                writable += 1
        return {
            "metadata": self.metadata,
            "point_count": len(self.points),
            "writable_point_count": writable,
            "reserved_range_count": len(self.reserved_ranges),
            "counts": counts,
        }


def apply_pcs_overrides(catalog: ProtocolCatalog, overrides_path: str | Path | None) -> ProtocolCatalog:
    if not overrides_path:
        return catalog
    path = Path(overrides_path)
    if not path.exists():
        return catalog
    overrides = json.loads(path.read_text(encoding="utf-8"))
    by_address = overrides.get("points", overrides)
    updated: list[dict[str, Any]] = []
    for original in catalog.points:
        point = dict(original)
        keys = [str(point.get("address_hex", "")).upper(), str(point.get("address"))]
        override = next((by_address[k] for k in keys if k in by_address), None)
        if isinstance(override, dict):
            point.update(override)
        updated.append(point)
    return ProtocolCatalog(metadata=dict(catalog.metadata), points=tuple(updated), reserved_ranges=catalog.reserved_ranges)
