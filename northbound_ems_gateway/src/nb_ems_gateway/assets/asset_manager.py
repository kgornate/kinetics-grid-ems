from __future__ import annotations

from typing import Any

from nb_ems_gateway.polling.poll_result import PollResult
from nb_ems_gateway.normalization.normalizer import normalize_poll_result
from .base_asset import AssetState


ASSET_DISPLAY_NAMES = {
    "existing_ems": "Existing EMS",
    "bms_1": "BMS 1",
    "pcs_1": "PCS 1",
    "utility_meter": "Utility Meter",
    "fire_protection": "Fire Protection",
    "liquid_cooling": "Liquid Cooling",
    "dehumidifier": "Dehumidifier",
    "io_module": "I/O Module",
    "remote_status": "Remote Status",
}


class AssetManager:
    def __init__(self) -> None:
        self.assets: dict[str, AssetState] = {
            asset_id: AssetState(asset_id=asset_id, display_name=name)
            for asset_id, name in ASSET_DISPLAY_NAMES.items()
        }

    def apply_poll_result(self, result: PollResult) -> None:
        normalized = normalize_poll_result(result)
        for asset_id, telemetry in normalized.items():
            if asset_id not in self.assets:
                self.assets[asset_id] = AssetState(asset_id=asset_id, display_name=asset_id)
            self.assets[asset_id].update(telemetry)

    def list_assets(self) -> list[dict[str, Any]]:
        return [asset.summary() for asset in self.assets.values()]

    def get_asset(self, asset_id: str, *, include_telemetry: bool = True, category: str | None = None) -> dict[str, Any] | None:
        asset = self.assets.get(asset_id)
        return asset.to_dict(include_telemetry=include_telemetry, category=category) if asset else None

    def asset_summary(self, asset_id: str) -> dict[str, Any] | None:
        asset = self.assets.get(asset_id)
        return asset.summary() if asset else None

    def telemetry_snapshot(self) -> dict[str, dict[str, Any]]:
        return {asset_id: asset.to_dict(include_telemetry=True) for asset_id, asset in self.assets.items()}

    def telemetry_payload(self) -> dict[str, dict[str, Any]]:
        return {asset_id: asset.telemetry for asset_id, asset in self.assets.items()}
