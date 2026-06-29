from __future__ import annotations

from collections import defaultdict
from typing import Any

from nb_ems_gateway.polling.poll_result import DecodedPointValue, PollResult


def normalize_poll_result(result: PollResult) -> dict[str, dict[str, Any]]:
    assets: dict[str, dict[str, Any]] = defaultdict(dict)
    for item in result.values:
        signal_key = item.normalized_name.split(".", 1)[1] if "." in item.normalized_name else item.normalized_name
        assets[item.asset_id][signal_key] = _telemetry_entry(item)
    return dict(assets)


def _telemetry_entry(item: DecodedPointValue) -> dict[str, Any]:
    return {
        "value": item.value,
        "unit": item.unit,
        "enum_text": item.enum_text,
        "quality": item.quality.value,
        "timestamp_utc": item.timestamp_utc,
        "address": item.address,
        "point_name": item.point_name,
        "display_name": item.display_name or item.point_name,
        "entity_name": item.entity_name,
        "category": item.category or "general",
        "dashboard_group": item.dashboard_group or "general",
        "is_key_signal": item.is_key_signal,
        "error": item.error,
    }


def flatten_values(values: list[DecodedPointValue] | tuple[DecodedPointValue, ...]) -> dict[str, Any]:
    return {item.normalized_name: item.value for item in values if item.value is not None}
