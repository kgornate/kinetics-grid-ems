from __future__ import annotations


def entity_to_asset_id(entity_name: str) -> str:
    name = entity_name.lower()
    if "ems system" in name:
        return "existing_ems"
    if name.startswith("bms") or "bms comm" in name:
        return "bms_1"
    if name == "pcs1" or name.startswith("pcs") or "pcs comm" in name:
        return "pcs_1"
    if "utility meter" in name:
        return "utility_meter"
    if "fire" in name:
        return "fire_protection"
    if "liquid cooling" in name:
        return "liquid_cooling"
    if "dehumidifier" in name:
        return "dehumidifier"
    if name.strip() in {"i/o", "io", "i o"}:
        return "io_module"
    if "remote control" in name:
        return "remote_status"
    return "existing_ems"


def entity_to_poll_group(entity_name: str, point_name: str) -> str:
    asset_id = entity_to_asset_id(entity_name)
    lower_point = point_name.lower()
    if asset_id in {"existing_ems", "pcs_1", "utility_meter", "fire_protection", "io_module"}:
        return "fast"
    if asset_id == "bms_1":
        if "cell voltage" in lower_point or "battery temperature" in lower_point:
            return "slow"
        return "fast"
    if asset_id == "liquid_cooling":
        return "default"
    if asset_id in {"dehumidifier", "remote_status"}:
        return "slow"
    return "default"
