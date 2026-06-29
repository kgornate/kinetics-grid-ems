from __future__ import annotations

from .alarm import Alarm


def evaluate_bms_alarms(asset: dict) -> list[Alarm]:
    alarms: list[Alarm] = []
    telemetry = asset.get("telemetry", {})
    for key, sample in telemetry.items():
        point = sample.get("point_name", "") if isinstance(sample, dict) else ""
        value = sample.get("value") if isinstance(sample, dict) else None
        if "insulation" in point.lower() and "too low" in point.lower() and value not in (None, 0):
            alarms.append(Alarm.create("bms_insulation_low", "critical", "bms_1", "BMS insulation low flag is active", key))
        if "contactor fault" in point.lower() and value not in (None, 0):
            alarms.append(Alarm.create("bms_contactor_fault", "critical", "bms_1", "BMS contactor fault flag is active", key))
    return alarms
