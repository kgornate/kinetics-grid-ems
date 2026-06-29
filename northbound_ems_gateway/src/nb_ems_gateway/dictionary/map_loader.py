from __future__ import annotations

import json
from pathlib import Path

from .register_map import RegisterMap
from .register_point import RegisterPoint


def load_register_map(path: str | Path) -> RegisterMap:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    points = [RegisterPoint.from_dict(item) for item in data["points"]]
    return RegisterMap.from_points(
        name=data.get("name", "china_ems_northbound"),
        version=data.get("version", "v1"),
        source_file=data.get("source_file"),
        points=points,
    )


def save_register_map(register_map: RegisterMap, path: str | Path) -> None:
    out = {
        "name": register_map.name,
        "version": register_map.version,
        "source_file": register_map.source_file,
        "point_count": register_map.point_count,
        "min_address": register_map.min_address,
        "max_address": register_map.max_address,
        "points": [p.to_dict() for p in register_map.points],
    }
    Path(path).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
