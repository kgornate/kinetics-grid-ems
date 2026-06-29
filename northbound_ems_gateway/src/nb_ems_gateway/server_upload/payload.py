from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_upload_payload(container: Any, *, payload_mode: str = "key_signals") -> dict[str, Any]:
    """Build the HTTPS REST payload sent to the backend server.

    payload_mode="key_signals" is the recommended default for cloud upload
    because it keeps the payload compact. payload_mode="full_snapshot" sends all
    normalized telemetry for all assets.
    """
    asset_snapshot = container.asset_manager.telemetry_snapshot()
    if payload_mode == "full_snapshot":
        assets_payload = asset_snapshot
    else:
        assets_payload = {
            asset_id: {
                "asset_id": asset.get("asset_id"),
                "display_name": asset.get("display_name"),
                "online": asset.get("online"),
                "last_update_utc": asset.get("last_update_utc"),
                "signal_count": asset.get("signal_count", 0),
                "bad_signal_count": asset.get("bad_signal_count", 0),
                "key_signals": asset.get("key_signals", {}),
            }
            for asset_id, asset in asset_snapshot.items()
        }

    return {
        "schema_version": "nb_ems_gateway.telemetry.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "gateway": {
            "id": container.config.gateway.id,
            "name": container.config.gateway.name,
            "mode": container.config.gateway.mode,
            "commands_enabled": container.config.api.commands_enabled,
        },
        "network": {
            "field_interface": container.config.network.field_interface,
            "application_interface": container.config.network.application_interface,
            "server_upload_interface": container.config.server_upload.network_interface,
        },
        "health": container.health_engine.snapshot(),
        "alarms": container.alarm_engine.snapshot(),
        "assets": assets_payload,
    }
