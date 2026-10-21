from __future__ import annotations

from typing import Any

from app.assets.mock_plant import MockPlant, now_iso
from app.core.catalog import ProtocolCatalog
from app.core.config import BmsConfig, PcsConfig, PcsDeviceConfig


class MockBmsControlDriver:
    """Driver-shaped adapter over MockPlant for software-in-the-loop control tests."""

    def __init__(self, config: BmsConfig, catalog: ProtocolCatalog, plant: MockPlant) -> None:
        self.config = config
        self.catalog = catalog
        self.plant = plant
        self.endpoints = {"bms_bank": object()}
        for rack in config.racks:
            self.endpoints[f"bms_rack_{rack.rack_id}"] = object()

    def read_point(self, asset_id: str, point_key: str) -> dict[str, Any]:
        if asset_id == "bms_bank":
            scope = "bank"
            index = 0
        elif asset_id.startswith("bms_rack_"):
            scope = "rack"
            index = int(asset_id.rsplit("_", 1)[1])
        else:
            scope = "environment"
            index = 0
        point = self.catalog.by_key(point_key, scope=scope)
        if not point:
            raise KeyError(f"Unknown mock BMS point: {point_key}")
        payload = self.plant.read_point(asset_id, point, asset_index=index)
        return {
            **payload,
            "asset_id": asset_id,
            "point_key": point_key,
            "address": point.get("address_hex"),
            "timestamp": now_iso(),
        }

    def write_point(self, asset_id: str, point_key: str, value: int | float) -> dict[str, Any]:
        scope = "bank" if asset_id == "bms_bank" else "rack" if asset_id.startswith("bms_rack_") else "environment"
        point = self.catalog.by_key(point_key, scope=scope)
        if not point:
            raise KeyError(f"Unknown mock BMS point: {point_key}")
        result = self.plant.write(asset_id, point, value)
        # Model the few control-side effects that Lineage exposes.
        if scope == "rack" and point_key in {"positive_contactor_command", "negative_contactor_command"}:
            if int(value) == 2:
                feedback = "positive_contactor_feedback" if point_key.startswith("positive") else "negative_contactor_feedback"
                self.plant.overrides[(asset_id, feedback)] = 0
            elif int(value) == 1:
                feedback = "positive_contactor_feedback" if point_key.startswith("positive") else "negative_contactor_feedback"
                self.plant.overrides[(asset_id, feedback)] = 1
        if scope == "bank" and point_key == "fault_reset" and int(value) == 1:
            self.plant.overrides[("bms_bank", "battery_system_state")] = 0xBBBB
        return {
            **result,
            "written_value": value,
            "readback": {"value": value},
        }


class MockPcsControlDriver:
    """PCS driver-shaped adapter over MockPlant for the Elecod digital twin."""

    def __init__(self, config: PcsConfig, catalog: ProtocolCatalog, plant: MockPlant) -> None:
        self.config = config
        self.catalog = catalog
        self.plant = plant
        self._devices = {device.asset_id: device for device in config.devices}

    def device(self, asset_id: str | None = None) -> PcsDeviceConfig:
        selected = asset_id or next(iter(self._devices))
        try:
            return self._devices[selected]
        except KeyError as error:
            raise KeyError(f"Unknown mock PCS asset: {selected}") from error

    def read_point(self, asset_id: str, point_key: str) -> dict[str, Any]:
        point = self.catalog.by_key(point_key, scope="pcs")
        if not point:
            raise KeyError(f"Unknown mock PCS point: {point_key}")
        payload = self.plant.read_point(asset_id, point)
        return {
            **payload,
            "asset_id": asset_id,
            "unit_id": self.device(asset_id).unit_id,
            "point_key": point_key,
            "address": point.get("address_hex"),
            "timestamp": now_iso(),
        }

    def write_point(self, asset_id: str, point_key: str, value: int | float) -> dict[str, Any]:
        point = self.catalog.by_key(point_key, scope="pcs")
        if not point:
            raise KeyError(f"Unknown mock PCS point: {point_key}")
        result = self.plant.write(asset_id, point, value)
        readback = self.read_point(asset_id, point_key) if point.get("readback_enabled", True) else None
        return {
            **result,
            "written_value": value,
            "readback": readback,
        }
