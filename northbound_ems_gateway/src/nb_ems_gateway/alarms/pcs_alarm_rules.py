from __future__ import annotations

from .alarm import Alarm


def evaluate_pcs_alarms(asset: dict) -> list[Alarm]:
    alarms: list[Alarm] = []
    telemetry = asset.get("telemetry", {})
    for key, sample in telemetry.items():
        point = sample.get("point_name", "") if isinstance(sample, dict) else ""
        value = sample.get("value") if isinstance(sample, dict) else None
        lower = point.lower()
        if "total fault status" in lower and value not in (None, 0):
            alarms.append(Alarm.create("pcs_total_fault", "critical", "pcs_1", "PCS total fault status is active", key))
        if "insulation resistance" in lower and value is not None and value < 1:
            alarms.append(Alarm.create("pcs_insulation_low", "warning", "pcs_1", "PCS insulation resistance may be low", key))
    return alarms
