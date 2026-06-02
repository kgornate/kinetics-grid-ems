#!/usr/bin/env python3
"""
PCS State Model

Purpose:
- Store the latest decoded PCS/Inverter state in a clean EMS-level format.
- This model is vendor-independent.
- Vendor-specific register decoding is handled inside drivers/pcs_profiles/*.py.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class PcsState:
    asset_id: str = "pcs_1"
    vendor: str = "njoy"

    comm_status: str = "offline"   # online / offline
    last_update_ts: str = ""
    error: str = ""

    # AC side values
    ab_voltage_v: Optional[float] = None
    bc_voltage_v: Optional[float] = None
    ca_voltage_v: Optional[float] = None

    phase_a_voltage_v: Optional[float] = None
    phase_b_voltage_v: Optional[float] = None
    phase_c_voltage_v: Optional[float] = None

    phase_a_current_a: Optional[float] = None
    phase_b_current_a: Optional[float] = None
    phase_c_current_a: Optional[float] = None

    frequency_hz: Optional[float] = None

    active_power_kw: Optional[float] = None
    reactive_power_kvar: Optional[float] = None
    apparent_power_kva: Optional[float] = None
    power_factor: Optional[float] = None

    # DC side values
    bus_voltage_v: Optional[float] = None
    battery_voltage_v: Optional[float] = None
    battery_current_a: Optional[float] = None
    dc_power_kw: Optional[float] = None
    dc_total_current_a: Optional[float] = None

    # Status
    operating_status_raw: Optional[int] = None
    operating_status: str = "unknown"

    grid_offgrid_status_raw: Optional[int] = None
    grid_offgrid_status: str = "unknown"

    fault_status: bool = False

    # Detailed NJOY/Enjoy fault words 0x1700..0x1707
    hardware_fault_word_1_raw: Optional[int] = None
    hardware_fault_word_2_raw: Optional[int] = None
    grid_fault_word_raw: Optional[int] = None
    bus_fault_word_raw: Optional[int] = None
    ac_capacitor_fault_word_raw: Optional[int] = None
    system_fault_word_raw: Optional[int] = None
    switch_fault_word_raw: Optional[int] = None
    other_fault_word_raw: Optional[int] = None

    fault_words_raw: Dict[str, Any] = field(default_factory=dict)
    fault_categories: Dict[str, Any] = field(default_factory=dict)
    active_faults: List[str] = field(default_factory=list)
    fault_count: int = 0
    detailed_fault_status: bool = False
    fault_words_read_error: str = ""

    # Temperature
    igbt_temperature_c: Optional[float] = None
    ambient_temperature_c: Optional[float] = None
    inductance_temperature_c: Optional[float] = None

    # Raw/latest vendor telemetry snapshot for debugging
    raw_telemetry: Dict[str, Any] = field(default_factory=dict)

    def update_from_telemetry(self, telemetry: Dict[str, Any]) -> None:
        """
        Update PCS state using decoded telemetry from vendor profile.
        """
        self.comm_status = "online"
        self.error = ""
        self.last_update_ts = now_iso()

        self.raw_telemetry = dict(telemetry)

        for key, value in telemetry.items():
            if hasattr(self, key):
                setattr(self, key, value)

        # Fault status normalization
        operating_status = str(telemetry.get("operating_status", "")).lower()
        grid_status = str(telemetry.get("grid_offgrid_status", "")).lower()

        telemetry_fault_status = telemetry.get("fault_status") is True
        detailed_fault_status = telemetry.get("detailed_fault_status") is True
        active_faults = telemetry.get("active_faults", [])
        has_active_faults = isinstance(active_faults, list) and len(active_faults) > 0

        self.fault_status = (
            telemetry_fault_status
            or detailed_fault_status
            or has_active_faults
            or operating_status == "fault"
            or grid_status == "fault"
            or "fault" in operating_status
            or "fault" in grid_status
        )

    def mark_offline(self, error: str = "") -> None:
        """
        Mark PCS communication as offline.
        """
        self.comm_status = "offline"
        self.error = error
        self.last_update_ts = now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)