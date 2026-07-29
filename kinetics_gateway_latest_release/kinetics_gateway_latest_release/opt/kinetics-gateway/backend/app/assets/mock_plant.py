from __future__ import annotations

import math
import random
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.core.catalog import ProtocolCatalog


SCENARIOS = {
    "normal",
    "charging",
    "discharging",
    "rack_communication_fault",
    "cell_overvoltage",
    "high_temperature",
    "emergency_stop",
    "cooling_fault",
    "pcs_fault",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def point_payload(point: dict[str, Any], value: Any, raw: Any | None = None, quality: str = "good") -> dict[str, Any]:
    raw_value = value if raw is None else raw
    bitfields = {}
    if isinstance(raw_value, int):
        bitfields = {bit["key"]: (raw_value >> int(bit["bit"])) & 1 for bit in point.get("bitfields", [])}
    return {
        "key": point.get("key"),
        "name_en": point.get("name_en"),
        "name_cn": point.get("name_cn"),
        "address": point.get("address_hex"),
        "value": value,
        "raw": raw_value,
        "unit": point.get("unit"),
        "quality": quality,
        "category": point.get("category"),
        "access": point.get("access"),
        "bitfields": bitfields,
    }


class MockPlant:
    def __init__(self, bms_catalog: ProtocolCatalog, pcs_catalog: ProtocolCatalog, rack_count: int = 4, seed: int = 93) -> None:
        self.bms_catalog = bms_catalog
        self.pcs_catalog = pcs_catalog
        self.rack_count = rack_count
        self.random = random.Random(seed)
        self.scenario = "normal"
        self.started = time.monotonic()
        self.overrides: dict[tuple[str, str], Any] = {}

    def set_scenario(self, scenario: str) -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"Unknown mock scenario: {scenario}")
        self.scenario = scenario

    def _base_numeric(self, point: dict[str, Any], asset_index: int = 0) -> float | int:
        key = str(point.get("key", "")).lower()
        unit = str(point.get("unit") or "").lower()
        t = time.monotonic() - self.started
        wobble = math.sin(t / 8.0 + asset_index) * 0.5

        fault_text = f"{key} {point.get('name_en', '')} {point.get('name_cn', '')}".lower()
        if any(token in fault_text for token in ["fault", "alarm", "emergency", "trip", "\u6545\u969c", "\u544a\u8b66", "\u62a5\u8b66", "\u6025\u505c"]):
            return 0

        if "soc" in key:
            return round(58.0 + asset_index * 0.4 + wobble, 1)
        if "soh" in key:
            return round(97.5 - asset_index * 0.2, 1)
        if "voltage" in key or "volt" in key or unit == "v":
            if "cell" in key or unit == "mv":
                return int(3290 + asset_index * 2 + wobble * 8)
            if "bank" in key or point.get("scope") == "bank":
                return round(1248.0 + wobble, 1)
            return round(312.0 + asset_index * 0.8 + wobble, 1)
        if "current" in key or "curr" in key or unit == "a":
            direction = -1 if self.scenario == "charging" else 1
            magnitude = 85.0 if self.scenario in {"charging", "discharging"} else 4.0
            return round(direction * magnitude + wobble, 1)
        if "power" in key or unit in {"kw", "kvar", "kva"}:
            direction = -1 if self.scenario == "charging" else 1
            magnitude = 100.0 if self.scenario in {"charging", "discharging"} else 5.0
            return round(direction * magnitude + wobble, 1)
        if "frequency" in key or unit == "hz":
            return round(50.0 + wobble * 0.02, 2)
        if "temperature" in key or "temp" in key or "℃" in str(point.get("unit")):
            return round(27.0 + asset_index + wobble, 1)
        if "humidity" in key or unit == "%rh":
            return round(55.0 + wobble, 1)
        if "energy" in key or unit in {"kwh", "mwh"}:
            return round(1500 + asset_index * 100 + t / 3600, 2)
        if "insulation" in key or key in {"ir", "positive_ir", "negative_ir"}:
            return 2500
        if "count" in key or "num" in key:
            return self.rack_count if point.get("scope") == "bank" else 16
        return 0

    def _value_for_point(self, point: dict[str, Any], asset_id: str, asset_index: int = 0) -> Any:
        override_key = (asset_id, str(point.get("key")))
        if override_key in self.overrides:
            return self.overrides[override_key]
        count = int(point.get("element_count") or 1)
        base = self._base_numeric(point, asset_index)
        if count == 1:
            return base
        key = str(point.get("key", "")).lower()
        values = []
        for index in range(count):
            if "vcell" in key or "cell" in key and "volt" in key:
                value = 3290 + ((index * 7 + asset_index * 3) % 35)
            elif "temp" in key:
                value = round(25.0 + ((index + asset_index) % 12) * 0.2, 1)
            else:
                value = base
            values.append(value)
        return values

    def _apply_scenario(self, asset_id: str, point: dict[str, Any], value: Any) -> tuple[Any, str]:
        key = str(point.get("key", "")).lower()
        quality = "good"
        if self.scenario == "rack_communication_fault" and asset_id == "bms_rack_2":
            return value, "bad"
        if self.scenario == "cell_overvoltage" and asset_id == "bms_rack_1":
            if key == "external_critical":
                value = int(value) | (1 << 2)
            if isinstance(value, list) and ("vcell" in key or "cell" in key and "volt" in key):
                value = list(value)
                if value:
                    value[7] = 3650
            if "max" in key and "cell" in key and "volt" in key:
                value = 3650
        if self.scenario == "high_temperature" and asset_id == "bms_rack_3":
            if key == "external_critical":
                value = int(value) | (1 << 6)
            if isinstance(value, list) and "temp" in key:
                value = list(value)
                if value:
                    value[3] = 58.0
            if "max" in key and "temp" in key:
                value = 58.0
        if self.scenario == "emergency_stop" and point.get("scope") == "bank" and key == "external_fault_state":
            value = int(value) | (1 << 6)
        if self.scenario == "cooling_fault" and point.get("scope") == "environment" and "liquid_cooling_comm_fault" in key:
            value = 1
        return value, quality

    def _asset_points(
        self,
        *,
        scope: str,
        asset_id: str,
        asset_index: int = 0,
        include_slow: bool = False,
        include_bulk: bool = False,
    ) -> dict[str, Any]:
        allowed = {"fast", "normal"}
        if include_slow:
            allowed.add("slow")
        if include_bulk:
            allowed.add("bulk")
        telemetry: dict[str, Any] = {}
        for point in self.bms_catalog.select(scope=scope, poll_classes=allowed):
            value = self._value_for_point(point, asset_id, asset_index)
            value, quality = self._apply_scenario(asset_id, point, value)
            telemetry[str(point["key"])] = point_payload(point, value, quality=quality)
        return telemetry

    def _split_environment(self, telemetry: dict[str, Any]) -> dict[str, dict[str, Any]]:
        groups = {
            "hvac": {},
            "liquid_cooling": {},
            "energy_meter": {},
            "dehumidifier_1": {},
            "dehumidifier_2": {},
            "safety_io": {},
            "environment_other": {},
        }
        for key, payload in telemetry.items():
            text = " ".join([key, str(payload.get("name_en") or ""), str(payload.get("name_cn") or "")]).lower()
            if key.startswith("dehumidifier2_") or any(token in text for token in ["dehumidifier2", "dehumidifier 2", "除湿机2", "chiller_fan2"]):
                group = "dehumidifier_2"
            elif key.startswith("dehumidifier_") or any(token in text for token in ["dehumidifier1", "dehumidifier 1", "除湿机1", "chiller_fan1"]):
                group = "dehumidifier_1"
            elif any(token in text for token in ["aircond", "air cond", "hvac", "air1", "空调"]):
                group = "hvac"
            elif any(token in text for token in ["liquid", "cooling", "coolant", "液冷"]):
                group = "liquid_cooling"
            elif any(token in text for token in ["meter", "电表", "frequency", "active power", "reactive power"]):
                group = "energy_meter"
            elif any(token in text for token in ["di", "do", "e-stop", "emergency", "fire", "water", "door", "breaker", "surge", "ups", "急停", "消防", "水浸"]):
                group = "safety_io"
            else:
                group = "environment_other"
            groups[group][key] = payload
        return groups

    def snapshot(self, *, include_slow: bool = False, include_bulk: bool = False) -> dict[str, Any]:
        timestamp = now_iso()
        bank = {
            "asset_id": "bms_bank",
            "asset_type": "bms_bank",
            "online": True,
            "timestamp": timestamp,
            "telemetry": self._asset_points(scope="bank", asset_id="bms_bank", include_slow=include_slow),
        }
        racks = []
        for rack_id in range(1, self.rack_count + 1):
            asset_id = f"bms_rack_{rack_id}"
            online = not (self.scenario == "rack_communication_fault" and rack_id == 2)
            racks.append(
                {
                    "asset_id": asset_id,
                    "asset_type": "bms_rack",
                    "rack_id": rack_id,
                    "bcu_unit_id": rack_id + 1,
                    "online": online,
                    "timestamp": timestamp,
                    "telemetry": self._asset_points(
                        scope="rack", asset_id=asset_id, asset_index=rack_id, include_slow=include_slow,
                        include_bulk=include_bulk,
                    ),
                }
            )
        env_all = self._asset_points(scope="environment", asset_id="bms_environment", include_slow=include_slow)
        env_groups = self._split_environment(env_all)
        environment = {
            key: {
                "asset_id": key,
                "asset_type": key,
                "online": not (self.scenario == "cooling_fault" and key == "liquid_cooling"),
                "timestamp": timestamp,
                "telemetry": values,
            }
            for key, values in env_groups.items()
        }
        pcs_telemetry: dict[str, Any] = {}
        for point in self.pcs_catalog.points:
            address = int(point["address"])
            point_text = f"{point.get('key', '')} {point.get('name_cn', '')} {point.get('name_en', '')}".lower()
            is_fault_point = any(token in point_text for token in ["fault", "alarm", "emergency", "trip", "故障", "告警", "报警", "急停"])
            value = 0 if is_fault_point else int(1000 + address + math.sin(time.monotonic() / 5) * 3)
            if self.scenario == "pcs_fault" and is_fault_point and 0x0026 <= address <= 0x003B:
                value = 1
            pcs_telemetry[str(point["key"])] = {
                "key": point["key"],
                "name_cn": point.get("name_cn"),
                "address": point.get("address_hex"),
                "raw": value,
                "value": value,
                "unit": point.get("unit"),
                "quality": "good",
                "decoding_status": "raw_only" if point.get("data_type") == "UNKNOWN" else "decoded",
            }
        pcs = {
            "asset_id": "pcs_1",
            "asset_type": "pcs",
            "online": True,
            "timestamp": timestamp,
            "telemetry": pcs_telemetry,
            "protocol_status": "raw_map_until_vendor_details_are_added",
        }
        return {
            "gateway_id": "kinetics_gateway_1",
            "mode": "mock",
            "scenario": self.scenario,
            "timestamp": timestamp,
            "bank": bank,
            "racks": racks,
            "environment": environment,
            "pcs": pcs,
        }

    def rack_details(self, rack_id: int) -> dict[str, Any]:
        asset_id = f"bms_rack_{rack_id}"
        return {
            "asset_id": asset_id,
            "rack_id": rack_id,
            "timestamp": now_iso(),
            "telemetry": self._asset_points(
                scope="rack", asset_id=asset_id, asset_index=rack_id, include_slow=True, include_bulk=True
            ),
        }

    def write(self, asset_id: str, point: dict[str, Any], value: Any) -> dict[str, Any]:
        self.overrides[(asset_id, str(point["key"]))] = deepcopy(value)
        return {
            "ok": True,
            "mock": True,
            "asset_id": asset_id,
            "point_key": point["key"],
            "value": value,
            "timestamp": now_iso(),
        }
