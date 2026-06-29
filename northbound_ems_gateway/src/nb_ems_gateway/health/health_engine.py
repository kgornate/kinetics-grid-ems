from __future__ import annotations

from nb_ems_gateway.assets.asset_manager import AssetManager


class HealthEngine:
    def __init__(self, asset_manager: AssetManager) -> None:
        self.asset_manager = asset_manager

    def snapshot(self) -> dict:
        assets = self.asset_manager.list_assets()
        online_count = sum(1 for asset in assets if asset["online"])
        total_signals = sum(asset.get("signal_count", 0) for asset in assets)
        bad_signals = sum(asset.get("bad_signal_count", 0) for asset in assets)
        return {
            "gateway_mode": "read_only",
            "asset_count": len(assets),
            "online_asset_count": online_count,
            "total_signal_count": total_signals,
            "bad_signal_count": bad_signals,
            "assets": [
                {
                    "asset_id": asset["asset_id"],
                    "display_name": asset["display_name"],
                    "online": asset["online"],
                    "last_update_utc": asset["last_update_utc"],
                    "signal_count": asset.get("signal_count", 0),
                    "bad_signal_count": asset.get("bad_signal_count", 0),
                }
                for asset in assets
            ],
        }
