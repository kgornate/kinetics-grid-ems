from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .register_point import RegisterPoint


@dataclass(frozen=True)
class RegisterMap:
    name: str
    version: str
    source_file: str | None
    points: tuple[RegisterPoint, ...]

    @property
    def point_count(self) -> int:
        return len(self.points)

    @property
    def min_address(self) -> int | None:
        return min((p.address for p in self.points), default=None)

    @property
    def max_address(self) -> int | None:
        return max((p.address + p.register_qty - 1 for p in self.points), default=None)

    def by_entity(self, entity_name: str) -> list[RegisterPoint]:
        return [p for p in self.points if p.entity_name == entity_name]

    def by_asset(self, asset_id: str) -> list[RegisterPoint]:
        return [p for p in self.points if p.asset_id == asset_id]

    def by_poll_group(self, poll_group: str) -> list[RegisterPoint]:
        return [p for p in self.points if p.poll_group == poll_group]

    def entities(self) -> list[str]:
        return sorted({p.entity_name for p in self.points})

    @classmethod
    def from_points(cls, name: str, version: str, points: Iterable[RegisterPoint], source_file: str | None = None) -> "RegisterMap":
        return cls(name=name, version=version, source_file=source_file, points=tuple(points))
