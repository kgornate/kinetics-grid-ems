"""
BMS / BCU State Model - Kinetics Grid EMS Gateway

Purpose:
- EMS-facing state object for the BMS/BCU asset.
- Consumes decoded payloads from drivers/bms_modbus_tcp_driver.py.
- Provides stable dictionaries for UDP telemetry, TCP READ commands, storage logging,
  and Flutter dashboard payloads.

Design rule:
- This model must not contain Modbus register addresses.
- Register addresses, scaling, bitfields, and control values belong only in
  drivers/bms_register_map.py.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

try:
    from drivers.bms_register_map import BMS_ASSET_ID
except ImportError:  # pragma: no cover - allows standalone testing
    BMS_ASSET_ID = "bms_1"


DEFAULT_GATEWAY_ID = "imx93_gateway_1"


def utc_now_iso() -> str:
    """Return timezone-aware UTC ISO timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool:
    return bool(value)


@dataclass
class BmsState:
    """Latest EMS-facing BMS state.

    This state is intentionally independent of Modbus. It represents the final
    clean asset data that the rest of the EMS stack should consume.
    """

    gateway_id: str = DEFAULT_GATEWAY_ID
    asset_id: str = BMS_ASSET_ID
    timestamp: str = field(default_factory=utc_now_iso)

    # Communication health
    communication_status: str = "unknown"  # online / offline / degraded / unknown
    last_error: Optional[str] = None
    last_success_ts: Optional[float] = None

    # Battery health and electrical telemetry
    soc_percent: Optional[float] = None
    soh_percent: Optional[float] = None
    rack_inner_soc_percent: Optional[float] = None
    rack_voltage_v: Optional[float] = None
    rack_current_a: Optional[float] = None
    power_kw: Optional[float] = None
    max_allowed_charge_current_a: Optional[float] = None
    max_allowed_discharge_current_a: Optional[float] = None

    # Cell voltage statistics
    max_cell_voltage_mv: Optional[float] = None
    min_cell_voltage_mv: Optional[float] = None
    avg_cell_voltage_mv: Optional[float] = None
    cell_voltage_diff_mv: Optional[float] = None

    # Thermal statistics
    max_cell_temp_c: Optional[float] = None
    min_cell_temp_c: Optional[float] = None
    avg_temp_c: Optional[float] = None
    max_temp_diff_c: Optional[float] = None

    # Insulation / safety
    insulation_resistance_kohm: Optional[float] = None
    positive_insulation_resistance_kohm: Optional[float] = None
    negative_insulation_resistance_kohm: Optional[float] = None

    # Operating status
    precharge_stage: Optional[str] = None
    bcu_state: Optional[str] = None
    current_state: Optional[str] = None
    heartbeat: Optional[int] = None
    contactor_active_flags: List[str] = field(default_factory=list)
    positive_contactor_closed: bool = False
    precharge_contactor_closed: bool = False
    negative_contactor_closed: bool = False

    # Alarm summary
    active_alarms: List[str] = field(default_factory=list)
    alarm_count: int = 0

    # Raw/diagnostic metadata for debugging, optional
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_driver_payload(
        cls,
        payload: Mapping[str, Any],
        gateway_id: str = DEFAULT_GATEWAY_ID,
        keep_raw: bool = False,
    ) -> "BmsState":
        """Create BmsState from BmsModbusTcpDriver.read_all() payload."""
        state = cls(
            gateway_id=gateway_id,
            asset_id=str(payload.get("asset_id", BMS_ASSET_ID)),
            timestamp=str(payload.get("timestamp", utc_now_iso())),
            communication_status=str(payload.get("communication_status", "online")),
            last_error=payload.get("last_error"),
            last_success_ts=_to_float(payload.get("last_success_ts")),
            soc_percent=_to_float(payload.get("soc_percent")),
            soh_percent=_to_float(payload.get("soh_percent")),
            rack_inner_soc_percent=_to_float(payload.get("rack_inner_soc_percent")),
            rack_voltage_v=_to_float(payload.get("rack_voltage_v")),
            rack_current_a=_to_float(payload.get("rack_current_a")),
            power_kw=_to_float(payload.get("power_kw")),
            max_allowed_charge_current_a=_to_float(payload.get("max_allowed_charge_current_a")),
            max_allowed_discharge_current_a=_to_float(payload.get("max_allowed_discharge_current_a")),
            max_cell_voltage_mv=_to_float(payload.get("max_cell_voltage_mv")),
            min_cell_voltage_mv=_to_float(payload.get("min_cell_voltage_mv")),
            avg_cell_voltage_mv=_to_float(payload.get("avg_cell_voltage_mv")),
            cell_voltage_diff_mv=_to_float(payload.get("cell_voltage_diff_mv")),
            max_cell_temp_c=_to_float(payload.get("max_cell_temp_c")),
            min_cell_temp_c=_to_float(payload.get("min_cell_temp_c")),
            avg_temp_c=_to_float(payload.get("avg_temp_c")),
            max_temp_diff_c=_to_float(payload.get("max_temp_diff_c")),
            insulation_resistance_kohm=_to_float(payload.get("insulation_resistance_kohm")),
            positive_insulation_resistance_kohm=_to_float(payload.get("positive_insulation_resistance_kohm")),
            negative_insulation_resistance_kohm=_to_float(payload.get("negative_insulation_resistance_kohm")),
            precharge_stage=payload.get("precharge_stage"),
            bcu_state=payload.get("bcu_state"),
            current_state=payload.get("current_state"),
            heartbeat=_to_int(payload.get("heartbeat")),
            contactor_active_flags=list(payload.get("contactor_active_flags") or []),
            positive_contactor_closed=_to_bool(payload.get("positive_contactor_closed")),
            precharge_contactor_closed=_to_bool(payload.get("precharge_contactor_closed")),
            negative_contactor_closed=_to_bool(payload.get("negative_contactor_closed")),
            active_alarms=list(payload.get("active_alarms") or []),
            alarm_count=_to_int(payload.get("alarm_count")) or len(list(payload.get("active_alarms") or [])),
            raw=dict(payload) if keep_raw else {},
        )
        state.recalculate_derived_fields()
        return state

    @classmethod
    def offline(
        cls,
        message: str,
        gateway_id: str = DEFAULT_GATEWAY_ID,
        asset_id: str = BMS_ASSET_ID,
        last_success_ts: Optional[float] = None,
    ) -> "BmsState":
        """Build an offline state when Modbus communication fails."""
        return cls(
            gateway_id=gateway_id,
            asset_id=asset_id,
            timestamp=utc_now_iso(),
            communication_status="offline",
            last_error=message,
            last_success_ts=last_success_ts,
            active_alarms=["bms_communication_lost"],
            alarm_count=1,
        )

    def recalculate_derived_fields(self) -> None:
        """Refresh calculated fields such as power and alarm count."""
        if self.rack_voltage_v is not None and self.rack_current_a is not None:
            self.power_kw = round((self.rack_voltage_v * self.rack_current_a) / 1000.0, 3)
        self.alarm_count = len(self.active_alarms)

    def is_online(self) -> bool:
        return self.communication_status.lower() == "online"

    def is_charging(self) -> bool:
        return (self.current_state or "").lower() == "charge" or (self.rack_current_a is not None and self.rack_current_a < 0)

    def is_discharging(self) -> bool:
        return (self.current_state or "").lower() == "discharge" or (self.rack_current_a is not None and self.rack_current_a > 0)

    def has_active_alarms(self) -> bool:
        return bool(self.active_alarms)

    def to_dict(self) -> Dict[str, Any]:
        """Full state dictionary for TCP READ_BMS_ALL and internal use."""
        self.recalculate_derived_fields()
        return asdict(self)

    def to_telemetry_dict(self) -> Dict[str, Any]:
        """Compact state payload for UDP telemetry and Flutter live dashboard."""
        self.recalculate_derived_fields()
        return {
            "gateway_id": self.gateway_id,
            "asset_id": self.asset_id,
            "timestamp": self.timestamp,
            "communication_status": self.communication_status,
            "soc_percent": self.soc_percent,
            "soh_percent": self.soh_percent,
            "rack_inner_soc_percent": self.rack_inner_soc_percent,
            "rack_voltage_v": self.rack_voltage_v,
            "rack_current_a": self.rack_current_a,
            "power_kw": self.power_kw,
            "max_allowed_charge_current_a": self.max_allowed_charge_current_a,
            "max_allowed_discharge_current_a": self.max_allowed_discharge_current_a,
            "max_cell_voltage_mv": self.max_cell_voltage_mv,
            "min_cell_voltage_mv": self.min_cell_voltage_mv,
            "avg_cell_voltage_mv": self.avg_cell_voltage_mv,
            "cell_voltage_diff_mv": self.cell_voltage_diff_mv,
            "max_cell_temp_c": self.max_cell_temp_c,
            "min_cell_temp_c": self.min_cell_temp_c,
            "avg_temp_c": self.avg_temp_c,
            "insulation_resistance_kohm": self.insulation_resistance_kohm,
            "precharge_stage": self.precharge_stage,
            "bcu_state": self.bcu_state,
            "current_state": self.current_state,
            "positive_contactor_closed": self.positive_contactor_closed,
            "precharge_contactor_closed": self.precharge_contactor_closed,
            "negative_contactor_closed": self.negative_contactor_closed,
            "active_alarms": self.active_alarms,
            "alarm_count": self.alarm_count,
            "last_error": self.last_error,
        }

    def to_log_row(self) -> Dict[str, Any]:
        """Flat row suitable for CSV telemetry logging."""
        data = self.to_telemetry_dict()
        data["active_alarms"] = ";".join(self.active_alarms)
        data["contactor_active_flags"] = ";".join(self.contactor_active_flags)
        return data

    def to_event_context(self) -> Dict[str, Any]:
        """Small context payload for command/alarm event logs."""
        return {
            "asset_id": self.asset_id,
            "timestamp": self.timestamp,
            "communication_status": self.communication_status,
            "soc_percent": self.soc_percent,
            "rack_voltage_v": self.rack_voltage_v,
            "rack_current_a": self.rack_current_a,
            "precharge_stage": self.precharge_stage,
            "bcu_state": self.bcu_state,
            "current_state": self.current_state,
            "alarm_count": self.alarm_count,
        }


# Default CSV column order for BMS telemetry logs.
BMS_LOG_FIELDS = [
    "timestamp",
    "gateway_id",
    "asset_id",
    "communication_status",
    "soc_percent",
    "soh_percent",
    "rack_inner_soc_percent",
    "rack_voltage_v",
    "rack_current_a",
    "power_kw",
    "max_allowed_charge_current_a",
    "max_allowed_discharge_current_a",
    "max_cell_voltage_mv",
    "min_cell_voltage_mv",
    "avg_cell_voltage_mv",
    "cell_voltage_diff_mv",
    "max_cell_temp_c",
    "min_cell_temp_c",
    "avg_temp_c",
    "insulation_resistance_kohm",
    "positive_insulation_resistance_kohm",
    "negative_insulation_resistance_kohm",
    "precharge_stage",
    "bcu_state",
    "current_state",
    "positive_contactor_closed",
    "precharge_contactor_closed",
    "negative_contactor_closed",
    "alarm_count",
    "active_alarms",
    "contactor_active_flags",
    "last_error",
]


__all__ = [
    "BmsState",
    "BMS_LOG_FIELDS",
    "DEFAULT_GATEWAY_ID",
    "utc_now_iso",
]
