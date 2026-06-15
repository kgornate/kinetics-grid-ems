"""
Telemetry composition helpers.

The important rule in this module is backward compatibility:
- Flutter currently expects chiller data at the top level when chiller exists.
- Newer dashboard/web clients can use packet["assets"], packet["pcs"], and
  packet["bms"].

Therefore this module intentionally preserves the old mixed packet shape while
centralizing the logic so main.py does not grow for every new asset.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional


JsonDict = Dict[str, Any]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def compose_legacy_udp_packet(
    *,
    gateway_id: str,
    mode: str,
    chiller_asset_id: str,
    pcs_asset_id: str,
    bms_asset_id: str,
    chiller_packet: Optional[JsonDict],
    pcs_packet: Optional[JsonDict],
    bms_packet: Optional[JsonDict],
    timestamp: Optional[str] = None,
) -> JsonDict:
    """
    Build the same UDP/web telemetry packet shape used before refactor.

    This function is pure and safe to unit-test. It does not read Modbus, does
    not touch sockets, and does not log.
    """
    ts = timestamp or now_iso()

    if chiller_packet is not None:
        packet = dict(chiller_packet)
        packet["gateway_id"] = gateway_id
        packet["timestamp"] = packet.get("timestamp", ts)
        packet["mode"] = mode
        packet["assets"] = {
            "chiller": chiller_packet,
            "pcs": pcs_packet,
            "bms": bms_packet,
        }
        packet["pcs"] = pcs_packet
        packet["bms"] = bms_packet
        return packet

    primary_asset_id = None
    if pcs_packet:
        primary_asset_id = pcs_asset_id
    elif bms_packet:
        primary_asset_id = bms_asset_id

    return {
        "type": "telemetry",
        "gateway_id": gateway_id,
        "asset_id": primary_asset_id,
        "timestamp": ts,
        "status": "ok" if (pcs_packet or bms_packet) else "error",
        "mode": mode,
        "data": {
            "message": "Combined PCS/BMS telemetry packet",
        },
        "assets": {
            "chiller": None,
            "pcs": pcs_packet,
            "bms": bms_packet,
        },
        "pcs": pcs_packet,
        "bms": bms_packet,
    }


def offline_asset_packet(
    *,
    gateway_id: str,
    asset_id: str,
    asset_type: str,
    error: str,
    timestamp: Optional[str] = None,
) -> JsonDict:
    """Standard offline payload for asset read exceptions."""
    ts = timestamp or now_iso()
    if asset_type == "chiller":
        return {
            "type": "telemetry",
            "gateway_id": gateway_id,
            "asset_id": asset_id,
            "timestamp": ts,
            "status": "error",
            "data": {
                "communication_status": "offline",
                "error": error,
            },
        }
    return {
        "asset_id": asset_id,
        "communication_status": "offline",
        "comm_status": "offline",
        "error": error,
    }
