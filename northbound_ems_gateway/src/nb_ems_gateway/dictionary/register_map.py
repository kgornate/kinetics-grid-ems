from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class RegisterPoint:
    id: str; asset_id: str; asset_display_name: str; address: int; register_qty: int
    point_name: str; signal_name: str; point_type: str; unit: str=""; description: str=""
    rw: int=0; factor: float=1.0; category: str="general"; key_signal: bool=False; entity_name: str=""
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegisterPoint":
        return cls(**{k:data.get(k) for k in cls.__dataclass_fields__})
    def to_dict(self) -> dict[str, Any]: return self.__dict__.copy()

@dataclass
class RegisterMap:
    name: str; version: str; points: list[RegisterPoint]; assets: list[dict[str,str]]; port: int=515; unit_id: int=1
    @classmethod
    def load(cls, path: str | Path) -> "RegisterMap":
        d=json.loads(Path(path).read_text())
        return cls(d.get('name','register_map'),d.get('version','unknown'),[RegisterPoint.from_dict(p) for p in d.get('points',[])],d.get('assets',[]),int(d.get('port',515)),int(d.get('unit_id',1)))
    @property
    def point_count(self) -> int: return len(self.points)
    def to_dict(self) -> dict[str,Any]:
        return {'name':self.name,'version':self.version,'point_count':self.point_count,'port':self.port,'unit_id':self.unit_id,'assets':self.assets,'points':[p.to_dict() for p in self.points]}
