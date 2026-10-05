from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class AssetCapabilities:
    """Vendor-neutral feature flags consumed by orchestration/application layers."""

    telemetry: bool = True
    alarms: bool = True
    writable: bool = False
    explicit_precharge_command: bool = False
    automatic_precharge_observable: bool = False
    forced_contactor_control: bool = False
    active_power_control: bool = False
    reactive_power_control: bool = False
    power_factor_control: bool = False
    on_grid_control: bool = False
    off_grid_control: bool = False
    grid_forming_vf: bool = False
    grid_forming_vsg: bool = False
    fault_reset: bool = False
    cell_level_telemetry: bool = False
    auxiliary_assets: bool = False
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class BatteryRackState:
    rack_id: int
    online: bool
    state_code: int | None
    state_label: str | None
    operating_state_code: int | None
    operating_state_label: str | None
    voltage_v: float | None
    current_a: float | None
    soc_percent: float | None
    soh_percent: float | None
    max_charge_power_kw: float | None
    max_discharge_power_kw: float | None
    max_charge_current_a: float | None
    max_discharge_current_a: float | None
    positive_contactor_closed: bool | None
    negative_contactor_closed: bool | None
    positive_insulation_mohm: float | None
    negative_insulation_mohm: float | None
    charge_allowed: bool
    discharge_allowed: bool
    blocking_reasons: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PcsState:
    asset_id: str
    online: bool
    running: bool | None
    charging: bool | None
    faulted: bool | None
    standby: bool | None
    shutdown: bool | None
    off_grid: bool | None
    dc_relay_connected: bool | None
    ac_relay_connected: bool | None
    dc_precharge_connected: bool | None
    actual_active_power_kw: float | None
    actual_reactive_power_kvar: float | None
    dc_voltage_v: float | None
    dc_current_a: float | None
    dc_bus_voltage_v: float | None
    raw_status: int | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PreparationResult:
    ok: bool
    command_issued: bool
    state: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class BatteryPairAdapter(Protocol):
    capabilities: AssetCapabilities

    def rack_state(self, rack_id: int) -> BatteryRackState: ...
    def prepare_for_operation(self, rack_id: int) -> PreparationResult: ...
    def disconnect(self, rack_id: int) -> PreparationResult: ...
    def fault_reset(self) -> dict[str, Any]: ...


@runtime_checkable
class PcsPairAdapter(Protocol):
    capabilities: AssetCapabilities

    def state(self, asset_id: str) -> PcsState: ...
    def configure_on_grid_pq(self, asset_id: str) -> list[dict[str, Any]]: ...
    def start(self, asset_id: str) -> dict[str, Any]: ...
    def stop(self, asset_id: str) -> dict[str, Any]: ...
    def standby(self, asset_id: str) -> dict[str, Any]: ...
    def shutdown(self, asset_id: str) -> dict[str, Any]: ...
    def set_active_power_kw(self, asset_id: str, power_kw: float) -> dict[str, Any]: ...
