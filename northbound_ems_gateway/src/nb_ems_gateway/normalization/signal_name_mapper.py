from __future__ import annotations

import re


def to_snake_case(text: str) -> str:
    text = text.strip().replace("/", " ").replace("-", " ")
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_").lower()


def normalize_signal_name(asset_id: str, point_name: str, unit: str | None = None) -> str:
    base = to_snake_case(point_name)
    suffix = _unit_suffix(unit)
    if suffix and not base.endswith("_" + suffix):
        base = f"{base}_{suffix}"
    return f"{asset_id}.{base}"


def _unit_suffix(unit: str | None) -> str | None:
    if not unit:
        return None
    unit_clean = unit.strip().lower()
    unit_map = {
        "%": "percent",
        "v": "v",
        "a": "a",
        "kw": "kw",
        "kvar": "kvar",
        "kva": "kva",
        "hz": "hz",
        "c": "c",
        "℃": "c",
        "kwh": "kwh",
        "mω": "mohm",
        "mohm": "mohm",
        "ω": "ohm",
        "ohm": "ohm",
    }
    return unit_map.get(unit_clean)
