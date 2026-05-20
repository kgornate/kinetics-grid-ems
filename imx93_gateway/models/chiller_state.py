from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class ChillerState:
    """
    Clean software data model for chiller telemetry.

    This model stores decoded engineering values,
    not raw Modbus register values.
    """

    water_pump: Optional[str] = None
    compressor1: Optional[str] = None
    compressor2: Optional[str] = None
    electric_heater: Optional[str] = None
    condensate_fan: Optional[str] = None
    makeup_pump: Optional[str] = None

    outlet_water_temp: Optional[float] = None
    return_water_temp: Optional[float] = None
    outlet_water_pressure: Optional[float] = None
    return_water_pressure: Optional[float] = None
    ambient_temp: Optional[float] = None

    fault_code: Optional[int] = None
    control_mode: Optional[int] = None
    set_temperature: Optional[float] = None

    communication_status: str = "unknown"
    last_update_time: Optional[str] = None

    def update_timestamp(self) -> None:
        self.last_update_time = datetime.now().isoformat(timespec="seconds")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_telemetry_packet(self, gateway_id: str, asset_id: str) -> Dict[str, Any]:
        """
        Creates final JSON telemetry packet to be sent over UDP.
        """
        return {
            "type": "telemetry",
            "gateway_id": gateway_id,
            "asset_id": asset_id,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "data": self.to_dict()
        }