from __future__ import annotations

from .alarm import Alarm


def evaluate_io_alarms(asset: dict) -> list[Alarm]:
    alarms: list[Alarm] = []
    telemetry = asset.get("telemetry", {})
    for key, sample in telemetry.items():
        point = sample.get("point_name", "") if isinstance(sample, dict) else ""
        value = sample.get("value") if isinstance(sample, dict) else None
        lower = point.lower()
        if "emergency stop" in lower and value not in (None, 0):
            alarms.append(Alarm.create("emergency_stop", "critical", "io_module", "Emergency stop signal is active", key))
        if "water" in lower and "alarm" in lower and value not in (None, 0):
            alarms.append(Alarm.create("water_ingress", "critical", "io_module", "Water ingress alarm is active", key))
    return alarms
