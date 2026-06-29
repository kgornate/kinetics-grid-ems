from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RegisterPoint:
    point_id: str
    channel_name: str | None
    port: int | None
    unit_id: int | None
    address: int
    register_qty: int
    group_no: int | None
    entity_name: str
    point_name: str
    point_type: str
    unit: str | None
    description: str | None
    rw_flag: int
    factor: float
    software_access: str = "read_only"
    normalized_name: str | None = None
    asset_id: str | None = None
    poll_group: str = "default"
    display_name: str | None = None
    category: str | None = None
    dashboard_group: str | None = None
    is_key_signal: bool = False
    enum_map: dict[str, str] | None = None

    @property
    def end_address_exclusive(self) -> int:
        return self.address + self.register_qty

    @property
    def is_vendor_marked_writable(self) -> bool:
        return self.rw_flag == 1

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegisterPoint":
        allowed = set(cls.__dataclass_fields__)
        clean = {key: value for key, value in data.items() if key in allowed}
        return cls(**clean)

    def to_dict(self) -> dict[str, Any]:
        return {
            "point_id": self.point_id,
            "channel_name": self.channel_name,
            "port": self.port,
            "unit_id": self.unit_id,
            "address": self.address,
            "register_qty": self.register_qty,
            "group_no": self.group_no,
            "entity_name": self.entity_name,
            "point_name": self.point_name,
            "point_type": self.point_type,
            "unit": self.unit,
            "description": self.description,
            "rw_flag": self.rw_flag,
            "factor": self.factor,
            "software_access": self.software_access,
            "normalized_name": self.normalized_name,
            "asset_id": self.asset_id,
            "poll_group": self.poll_group,
            "display_name": self.display_name,
            "category": self.category,
            "dashboard_group": self.dashboard_group,
            "is_key_signal": self.is_key_signal,
            "enum_map": self.enum_map,
        }
