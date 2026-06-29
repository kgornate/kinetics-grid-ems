from __future__ import annotations

from .alarm import Alarm


def evaluate_fire_alarms(asset: dict) -> list[Alarm]:
    alarms: list[Alarm] = []
    telemetry = asset.get("telemetry", {})
    for key, sample in telemetry.items():
        point = sample.get("point_name", "") if isinstance(sample, dict) else ""
        value = sample.get("value") if isinstance(sample, dict) else None
        if any(word in point.lower() for word in ["alarm", "fire", "co"]):
            if value not in (None, 0):
                alarms.append(Alarm.create("fire_alarm_active", "critical", "fire_protection", f"Fire protection signal active: {point}", key))
    return alarms
