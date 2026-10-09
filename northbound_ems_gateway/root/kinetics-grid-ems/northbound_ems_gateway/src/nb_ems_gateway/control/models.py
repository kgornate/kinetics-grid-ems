from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

GridMode = Literal['grid_tied', 'off_grid']
PowerOperation = Literal['charge', 'discharge']
AllocationMode = Literal['equal', 'custom']

class GridModeRequest(BaseModel):
    target_mode: GridMode
    readback: bool = True
    timeout_sec: float | None = None
    wait_for_voltage_stable: bool = True
    note: str | None = None

class SiteGridModeRequest(BaseModel):
    target_mode: GridMode
    source_ids: list[str] | None = None
    source_order: list[str] | None = None
    execution: Literal['parallel', 'sequential'] | None = None
    readback: bool = True
    timeout_sec: float | None = None
    wait_for_voltage_stable: bool = True
    inter_source_delay_sec: float | None = None
    note: str | None = None

class PowerCommandRequest(BaseModel):
    power_kw: float = Field(..., gt=0)
    readback: bool = True
    note: str | None = None

class SitePowerCommandRequest(BaseModel):
    operation: PowerOperation
    source_ids: list[str] | None = None
    total_power_kw: float = Field(..., gt=0)
    allocation: AllocationMode = 'equal'
    per_source_power_kw: dict[str, float] | None = None
    readback: bool = True
    note: str | None = None

class StandbyRequest(BaseModel):
    readback: bool = True
    note: str | None = None

class SiteStandbyRequest(BaseModel):
    source_ids: list[str] | None = None
    readback: bool = True
    note: str | None = None
