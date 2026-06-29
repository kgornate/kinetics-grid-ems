from __future__ import annotations

from .alarm import Alarm


def evaluate_cooling_alarms(asset: dict) -> list[Alarm]:
    alarms: list[Alarm] = []
    telemetry = asset.get("telemetry", {})
    for key, sample in telemetry.items():
        point = sample.get("point_name", "") if isinstance(sample, dict) else ""
        value = sample.get("value") if isinstance(sample, dict) else None
        if "alarm" in point.lower() and value not in (None, 0):
            alarms.append(Alarm.create("cooling_alarm_active", "warning", "liquid_cooling", f"Cooling alarm active: {point}", key))
    return alarms
