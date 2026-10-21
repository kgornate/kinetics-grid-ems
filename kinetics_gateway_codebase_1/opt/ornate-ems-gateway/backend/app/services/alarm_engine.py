from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


FAULT_TOKENS = [
    "fault", "alarm", "warn", "stop", "shutdown", "prohibit", "protection", "emergency", "trip", "fire",
    "malfunction", "failure", "invalid", "abnormal",
    "\u6545\u969c",  # fault
    "\u544a\u8b66",  # alarm
    "\u62a5\u8b66",  # alarm
    "\u6025\u505c",  # emergency stop
]


def severity_from_text(text: str) -> str:
    lower = text.lower()
    if any(token in lower for token in ["critical", "emergency", "stop", "shutdown", "trip", "fire", "combustible gas", "protection", "level 1", "lvl1", "\u6025\u505c"]):
        return "critical"
    if any(token in lower for token in ["fault", "alarm", "level 2", "lvl2", "\u6545\u969c", "\u544a\u8b66", "\u62a5\u8b66"]):
        return "alarm"
    return "warning"


class AlarmEngine:
    def extract(self, asset: dict[str, Any]) -> list[dict[str, Any]]:
        alarms: list[dict[str, Any]] = []
        asset_id = str(asset.get("asset_id"))
        asset_type = str(asset.get("asset_type") or "")
        if not asset.get("online", True):
            alarms.append(
                self._alarm(asset_id, "communication_offline", "critical", f"{asset_id} communication is offline")
            )
        for key, point in (asset.get("telemetry") or {}).items():
            if point.get("quality") == "bad":
                continue
            bitfields = point.get("bitfields") or {}
            for child_key, bit_value in bitfields.items():
                if int(bit_value) != 1:
                    continue
                text = f"{key} {child_key} {point.get('name_en') or ''} {point.get('name_cn') or ''}"
                if not any(token in text.lower() for token in FAULT_TOKENS):
                    continue
                alarms.append(
                    self._alarm(
                        asset_id,
                        f"{key}.{child_key}",
                        severity_from_text(text),
                        f"{asset_id}: {child_key.replace('_', ' ')} active",
                        {"point_key": key, "bit_key": child_key, "address": point.get("address")},
                    )
                )

            # Some protocols expose direct 0/1 alarm inputs rather than packed
            # bitfields. Limit interpretation to alarm/signal categories so a
            # writable setting whose name happens to contain "fault" can never
            # become a false live alarm. Lineage System/Rack Alarm points are
            # FC02 discrete inputs and belong here.
            value = point.get("value")
            text = f"{key} {point.get('name_en') or ''} {point.get('name_cn') or ''}"
            category = str(point.get("category") or "").lower()
            is_direct_fault_name = any(token in text.lower() for token in FAULT_TOKENS)
            direct_scope_allowed = category in {"signal", "alarm", "system_alarm", "rack_alarm"}
            if asset_type.startswith("bms_") and category == "system_data":
                # Lineage duplicates selected FSS/UPS/gas dry contacts inside
                # System Data. Only names that explicitly carry fault/alarm/warn
                # semantics are promoted to alarms.
                direct_scope_allowed = is_direct_fault_name
            if not bitfields and direct_scope_allowed and is_direct_fault_name and isinstance(value, (int, float)) and value != 0:
                alarms.append(
                    self._alarm(
                        asset_id,
                        str(key),
                        severity_from_text(text),
                        f"{asset_id}: {point.get('name_en') or point.get('name_cn') or key} active",
                        {"point_key": key, "address": point.get("address"), "value": value},
                    )
                )
        return alarms

    @staticmethod
    def _alarm(
        asset_id: str,
        code: str,
        severity: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "alarm_key": f"{asset_id}:{code}",
            "asset_id": asset_id,
            "code": code,
            "severity": severity,
            "active": True,
            "raised_at": now_iso(),
            "cleared_at": None,
            "message": message,
            "payload": payload or {},
        }
