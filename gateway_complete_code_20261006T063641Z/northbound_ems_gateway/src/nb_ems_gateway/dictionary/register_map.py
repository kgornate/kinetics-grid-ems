from __future__ import annotations
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class RegisterPoint:
    id: str
    asset_id: str
    asset_display_name: str
    address: int
    register_qty: int
    point_name: str
    signal_name: str
    point_type: str
    unit: str = ""
    description: str = ""
    rw: int = 0
    factor: float = 1.0
    category: str = "general"
    key_signal: bool = False
    entity_name: str = ""
    source_id: str = ""
    source_display_name: str = ""
    base_asset_id: str = ""
    base_signal_name: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegisterPoint":
        values: dict[str, Any] = {}
        for k, field in cls.__dataclass_fields__.items():
            if k in data:
                values[k] = data[k]
            elif field.default is not field.default_factory:  # type: ignore[attr-defined]
                values[k] = field.default
        return cls(**values)

    def with_source(self, source_id: str, source_display_name: str, asset_id: str, asset_display_name: str) -> "RegisterPoint":
        return replace(
            self,
            id=f"{source_id}:{self.id}",
            source_id=source_id,
            source_display_name=source_display_name,
            base_asset_id=self.asset_id,
            base_signal_name=self.signal_name,
            asset_id=asset_id,
            asset_display_name=asset_display_name,
        )

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

@dataclass
class RegisterMap:
    name: str
    version: str
    points: list[RegisterPoint]
    assets: list[dict[str,str]]
    port: int = 502
    unit_id: int = 1
    source: str = ""

    @classmethod
    def load(cls, path: str | Path) -> "RegisterMap":
        d = json.loads(Path(path).read_text())
        return cls(
            d.get('name','register_map'),
            d.get('version','unknown'),
            [RegisterPoint.from_dict(p) for p in d.get('points',[])],
            d.get('assets',[]),
            int(d.get('port',502)),
            int(d.get('unit_id',1)),
            d.get('source',''),
        )

    @property
    def point_count(self) -> int:
        return len(self.points)

    @property
    def writable_points(self) -> list[RegisterPoint]:
        return [p for p in self.points if int(p.rw or 0) == 1]

    def find_point(self, *, signal_name: str | None = None, address: int | None = None, asset_id: str | None = None) -> RegisterPoint | None:
        for p in self.points:
            if signal_name is not None and p.signal_name != signal_name:
                continue
            if address is not None and p.address != address:
                continue
            if asset_id is not None and p.asset_id != asset_id:
                continue
            return p
        return None

    def require_point(self, *, signal_name: str | None = None, address: int | None = None, asset_id: str | None = None) -> RegisterPoint:
        p = self.find_point(signal_name=signal_name, address=address, asset_id=asset_id)
        if not p:
            target = signal_name if signal_name is not None else address
            raise KeyError(f"Register point not found: {target}")
        return p

    def to_dict(self) -> dict[str,Any]:
        return {
            'name':self.name,
            'version':self.version,
            'source':self.source,
            'point_count':self.point_count,
            'writable_point_count':len(self.writable_points),
            'port':self.port,
            'unit_id':self.unit_id,
            'assets':self.assets,
            'points':[p.to_dict() for p in self.points],
        }
