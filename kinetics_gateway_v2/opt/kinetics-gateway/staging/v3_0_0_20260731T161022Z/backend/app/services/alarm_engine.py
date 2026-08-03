from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


FAULT_TOKENS = [
    "fault", "alarm", "warn", "stop", "shutdown", "prohibit", "emergency", "trip",
    "\u6545\u969c",  # fault
    "\u544a\u8b66",  # alarm
    "\u62a5\u8b66",  # alarm
    "\u6025\u505c",  # emergency stop
]


def severity_from_text(text: str) -> str:
    lower = text.lower()
    if any(token in lower for token in ["critical", "emergency", "stop", "shutdown", "trip", "level 1", "lvl1", "\u6025\u505c"]):
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

            # Some points are direct 0/1 fault flags rather than bitfields. Avoid
            # interpreting protection-setting values as alarms by limiting this to
            # PCS fault words and signal-category telemetry.
            value = point.get("value")
            text = f"{key} {point.get('name_en') or ''} {point.get('name_cn') or ''}"
            is_direct_fault_name = any(token in text.lower() for token in FAULT_TOKENS)
            direct_scope_allowed = asset_type == "pcs" or str(point.get("category") or "").lower() == "signal"
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
