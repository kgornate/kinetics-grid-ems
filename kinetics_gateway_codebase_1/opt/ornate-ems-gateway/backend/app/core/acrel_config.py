from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator


class AcrelMeterConfig(BaseModel):
    """Independent read-only meter; hardware mode is explicit, even with mock BESS."""

    enabled: bool = False
    asset_id: Literal["acrel_meter_1"] = "acrel_meter_1"
    label: str = "ACREL APM520"
    location: str = "unassigned"
    mode: Literal["hardware", "mock"] = "hardware"
    device: str = "/dev/ttyLP6"
    unit_id: int = Field(1, ge=1, le=247)
    baudrate: Literal[1200, 2400, 4800, 9600, 19200, 38400, 57600] = 9600
    parity: Literal["N", "E", "O"] = "N"
    stopbits: Literal[1, 2] = 1
    word_order: Literal["big", "lsw_first"] = "big"
    timeout_seconds: float = Field(2.0, ge=0.1, le=10, allow_inf_nan=False)
    retries: int = Field(1, ge=0, le=2)
    poll_seconds: float = Field(5.0, ge=1, le=3600, allow_inf_nan=False)
    stale_after_seconds: float = Field(20.0, ge=1, le=86400, allow_inf_nan=False)
    energy_enabled: bool = True
    energy_poll_seconds: float = Field(60.0, ge=5, le=86400, allow_inf_nan=False)
    # Hardware data is stored as reported. CT/PT ratios are configured on the
    # meter, not multiplied a second time here. Commission against its display.
    scaling_validated: bool = False

    @model_validator(mode="after")
    def validate_meter(self):
        if not self.device.startswith("/dev/") or self.device == "/dev/ttyLP0":
            raise ValueError("Meter requires a serial /dev path other than the DEBIX console")
        if self.stale_after_seconds <= self.poll_seconds:
            raise ValueError("Meter stale threshold must exceed poll interval")
        if self.energy_poll_seconds < self.poll_seconds:
            raise ValueError("Energy interval must be at least the measurement poll interval")
        return self
