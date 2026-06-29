from __future__ import annotations

from nb_ems_gateway.assets.asset_manager import AssetManager
from .alarm import Alarm
from .bms_alarm_rules import evaluate_bms_alarms
from .cooling_alarm_rules import evaluate_cooling_alarms
from .fire_alarm_rules import evaluate_fire_alarms
from .io_alarm_rules import evaluate_io_alarms
from .pcs_alarm_rules import evaluate_pcs_alarms


class AlarmEngine:
    def __init__(self, asset_manager: AssetManager) -> None:
        self.asset_manager = asset_manager

    def evaluate(self) -> list[Alarm]:
        snapshot = self.asset_manager.telemetry_snapshot()
        alarms: list[Alarm] = []
        if "bms_1" in snapshot:
            alarms.extend(evaluate_bms_alarms(snapshot["bms_1"]))
        if "pcs_1" in snapshot:
            alarms.extend(evaluate_pcs_alarms(snapshot["pcs_1"]))
        if "fire_protection" in snapshot:
            alarms.extend(evaluate_fire_alarms(snapshot["fire_protection"]))
        if "liquid_cooling" in snapshot:
            alarms.extend(evaluate_cooling_alarms(snapshot["liquid_cooling"]))
        if "io_module" in snapshot:
            alarms.extend(evaluate_io_alarms(snapshot["io_module"]))
        return alarms

    def snapshot(self) -> dict:
        alarms = self.evaluate()
        return {
            "count": len(alarms),
            "alarms": [alarm.to_dict() for alarm in alarms],
        }
