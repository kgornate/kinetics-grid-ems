from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.core.config import GatewayConfig


LINEAGE_STATE_LABELS = {
    0x1111: "NoChg",
    0x2222: "NoDchg",
    0x5555: "Standby",
    0xAAAA: "Fault",
    0xBBBB: "Normal",
    0xCCCC: "Warn",
}
LINEAGE_OPERATING_LABELS = {1: "Open", 2: "Standby", 3: "Charge", 4: "Discharge"}


def _point(asset: dict[str, Any] | None, key: str) -> dict[str, Any] | None:
    if not isinstance(asset, dict):
        return None
    value = (asset.get("telemetry") or {}).get(key)
    return value if isinstance(value, dict) else None


def _value(asset: dict[str, Any] | None, key: str) -> Any:
    point = _point(asset, key)
    return None if point is None else point.get("value")


def _number(asset: dict[str, Any] | None, key: str) -> float | None:
    value = _value(asset, key)
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _int(asset: dict[str, Any] | None, key: str) -> int | None:
    value = _value(asset, key)
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _bool(asset: dict[str, Any] | None, key: str) -> bool | None:
    value = _value(asset, key)
    if value is None:
        return None
    try:
        return bool(int(value))
    except (TypeError, ValueError):
        return None


def _status_bit(asset: dict[str, Any] | None, bit: int, *aliases: str) -> bool | None:
    status = _point(asset, "status_word")
    if status is None:
        return None
    bitfields = status.get("bitfields") or {}
    for alias in aliases:
        if alias in bitfields:
            return bool(int(bitfields[alias]))
    raw = status.get("raw")
    if raw is None:
        raw = status.get("value")
    try:
        return bool((int(raw) >> bit) & 1)
    except (TypeError, ValueError):
        return None


def lineage_system_view(bank: dict[str, Any]) -> dict[str, Any]:
    state_code = _int(bank, "battery_system_state")
    return {
        "asset_id": bank.get("asset_id", "bms_bank"),
        "online": bool(bank.get("online", False)),
        "timestamp": bank.get("timestamp"),
        "state_code": state_code,
        "state": LINEAGE_STATE_LABELS.get(state_code),
        "installed_racks": _int(bank, "installed_rack_count"),
        "operating_racks": _int(bank, "operating_rack_count"),
        "operating_rack_bitmap": _int(bank, "operating_rack_bitmap"),
        "voltage_v": _number(bank, "system_voltage"),
        "current_a": _number(bank, "system_current"),
        "soc_percent": _number(bank, "system_soc"),
        "soh_percent": _number(bank, "system_soh"),
        "max_charge_power_kw": _number(bank, "system_max_charge_power"),
        "max_discharge_power_kw": _number(bank, "system_max_discharge_power"),
        "max_charge_current_a": _number(bank, "system_max_charge_current"),
        "max_discharge_current_a": _number(bank, "system_max_discharge_current"),
        "max_cell_voltage_v": _number(bank, "system_max_cell_voltage"),
        "min_cell_voltage_v": _number(bank, "system_min_cell_voltage"),
        "max_cell_temperature_c": _number(bank, "system_max_cell_temperature"),
        "min_cell_temperature_c": _number(bank, "system_min_cell_temperature"),
        "accumulated_charge_energy_kwh": _number(bank, "system_accumulated_charge_energy"),
        "accumulated_discharge_energy_kwh": _number(bank, "system_accumulated_discharge_energy"),
    }


def lineage_rack_view(rack: dict[str, Any]) -> dict[str, Any]:
    state_code = _int(rack, "rack_state")
    operating_code = _int(rack, "rack_operating_state")
    charge_allowed = state_code not in {None, 0x1111, 0x5555, 0xAAAA}
    discharge_allowed = state_code not in {None, 0x2222, 0x5555, 0xAAAA}
    blockers: list[str] = []
    if not rack.get("online", False):
        blockers.append("communication_offline")
    if state_code == 0x1111:
        blockers.append("bms_no_charge")
    elif state_code == 0x2222:
        blockers.append("bms_no_discharge")
    elif state_code == 0x5555:
        blockers.append("bms_standby")
    elif state_code == 0xAAAA:
        blockers.append("bms_fault")
    elif state_code == 0xCCCC:
        blockers.append("bms_warning_vendor_policy_required")
    return {
        "asset_id": rack.get("asset_id"),
        "rack_id": rack.get("rack_id"),
        "online": bool(rack.get("online", False)),
        "timestamp": rack.get("timestamp"),
        "state_code": state_code,
        "state": LINEAGE_STATE_LABELS.get(state_code),
        "operating_state_code": operating_code,
        "operating_state": LINEAGE_OPERATING_LABELS.get(operating_code),
        "voltage_v": _number(rack, "rack_voltage"),
        "current_a": _number(rack, "rack_current"),
        "soc_percent": _number(rack, "rack_soc"),
        "soh_percent": _number(rack, "rack_soh"),
        "max_charge_power_kw": _number(rack, "rack_max_charge_power"),
        "max_discharge_power_kw": _number(rack, "rack_max_discharge_power"),
        "max_charge_current_a": _number(rack, "rack_max_charge_current"),
        "max_discharge_current_a": _number(rack, "rack_max_discharge_current"),
        "positive_contactor_closed": _bool(rack, "positive_contactor_feedback"),
        "negative_contactor_closed": _bool(rack, "negative_contactor_feedback"),
        "positive_insulation_mohm": _number(rack, "positive_insulation_resistance"),
        "negative_insulation_mohm": _number(rack, "negative_insulation_resistance"),
        "max_cell_voltage_v": _number(rack, "rack_max_cell_voltage"),
        "min_cell_voltage_v": _number(rack, "rack_min_cell_voltage"),
        "max_cell_temperature_c": _number(rack, "rack_max_cell_temperature"),
        "min_cell_temperature_c": _number(rack, "rack_min_cell_temperature"),
        "charge_allowed": charge_allowed and bool(rack.get("online", False)),
        "discharge_allowed": discharge_allowed and bool(rack.get("online", False)),
        "blocking_reasons": blockers,
    }


def elecod_pcs_view(pcs: dict[str, Any]) -> dict[str, Any]:
    running = _status_bit(pcs, 6, "operation_status", "running")
    charging = _status_bit(pcs, 5, "chargeand_discharge", "charging")
    faulted = _status_bit(pcs, 7, "faultstatus", "fault")
    return {
        "asset_id": pcs.get("asset_id"),
        "label": pcs.get("label"),
        "online": bool(pcs.get("online", False)),
        "timestamp": pcs.get("timestamp"),
        "running": running,
        "charging": charging if running else None,
        "discharging": (not charging) if charging is not None and running else None,
        "faulted": faulted,
        "standby": _status_bit(pcs, 10, "standby"),
        "shutdown": _status_bit(pcs, 11, "shutdown"),
        "off_grid": _status_bit(pcs, 4, "off_grid"),
        "dc_precharge_connected": _status_bit(pcs, 0, "dcpre_charge", "dc_precharge_connected"),
        "dc_relay_connected": _status_bit(pcs, 2, "dcrelay", "dc_relay_connected"),
        "ac_relay_connected": _status_bit(pcs, 3, "acrelay", "ac_relay_connected"),
        "active_power_kw": _number(pcs, "total_active_power"),
        "reactive_power_kvar": _number(pcs, "total_reactive_power"),
        "power_factor": _number(pcs, "total_power_factor"),
        "dc_voltage_v": _number(pcs, "dc_voltage"),
        "dc_current_a": _number(pcs, "dc_current"),
        "dc_power_kw": _number(pcs, "dc_power"),
        "dc_bus_voltage_v": _number(pcs, "dc_bus_voltage"),
        "grid_frequency_hz": _number(pcs, "grid_frequency_a"),
        "grid_voltage_ab_v": _number(pcs, "grid_voltage_ab"),
        "grid_voltage_bc_v": _number(pcs, "grid_voltage_bc"),
        "grid_voltage_ca_v": _number(pcs, "grid_voltage_ca"),
    }


def build_normalized_snapshot(snapshot: dict[str, Any], config: GatewayConfig) -> dict[str, Any]:
    """Build vendor-neutral read-only views from the shared runtime cache.

    This function never performs fieldbus I/O. Phase 4 therefore exposes a
    stable application/API contract without adding extra Modbus reads on every
    HTTP request or WebSocket client.
    """

    bank = snapshot.get("bank") if isinstance(snapshot.get("bank"), dict) else {}
    rack_assets = {
        int(item.get("rack_id")): item
        for item in snapshot.get("racks", [])
        if isinstance(item, dict) and item.get("rack_id") is not None
    }
    pcs_assets = snapshot.get("pcs_devices", {}) if isinstance(snapshot.get("pcs_devices"), dict) else {}

    battery_system = lineage_system_view(bank) if config.bms.vendor.lower() == "lineage" else {
        "asset_id": bank.get("asset_id", "bms_bank"),
        "online": bool(bank.get("online", False)),
        "timestamp": bank.get("timestamp"),
        "vendor": config.bms.vendor,
    }

    racks: dict[str, Any] = {}
    for rack_id, asset in rack_assets.items():
        view = lineage_rack_view(asset) if config.bms.vendor.lower() == "lineage" else {
            "asset_id": asset.get("asset_id"),
            "rack_id": rack_id,
            "online": bool(asset.get("online", False)),
            "timestamp": asset.get("timestamp"),
            "vendor": config.bms.vendor,
        }
        racks[str(rack_id)] = view

    pcs: dict[str, Any] = {}
    for asset_id, asset in pcs_assets.items():
        view = elecod_pcs_view(asset) if config.pcs.vendor.lower() == "elecod" else {
            "asset_id": asset_id,
            "online": bool(asset.get("online", False)),
            "timestamp": asset.get("timestamp"),
            "vendor": config.pcs.vendor,
        }
        pcs[asset_id] = view

    pairs: dict[str, Any] = {}
    for pair in config.control_sequence.pairs:
        rack = racks.get(str(pair.rack_id), {})
        pcs_view = pcs.get(pair.pcs_asset_id, {})
        pair_online = bool(rack.get("online")) and bool(pcs_view.get("online"))
        pairs[pair.pair_id] = {
            "pair_id": pair.pair_id,
            "enabled": pair.enabled,
            "rack_id": pair.rack_id,
            "pcs_asset_id": pair.pcs_asset_id,
            "online": pair_online,
            "battery": deepcopy(rack),
            "pcs": deepcopy(pcs_view),
            "charge_available_kw": rack.get("max_charge_power_kw") if rack.get("charge_allowed") else 0.0,
            "discharge_available_kw": rack.get("max_discharge_power_kw") if rack.get("discharge_allowed") else 0.0,
        }

    auxiliary = {
        asset_id: {
            "asset_id": asset.get("asset_id"),
            "asset_type": asset.get("asset_type"),
            "online": bool(asset.get("online", False)),
            "timestamp": asset.get("timestamp"),
            "telemetry": deepcopy(asset.get("telemetry", {})),
        }
        for asset_id, asset in (snapshot.get("environment") or {}).items()
        if isinstance(asset, dict)
    }

    return {
        "gateway_id": snapshot.get("gateway_id"),
        "timestamp": snapshot.get("timestamp"),
        "sequence": snapshot.get("sequence"),
        "vendors": {"bms": config.bms.vendor, "pcs": config.pcs.vendor},
        "battery_system": battery_system,
        "battery_racks": racks,
        "pcs": pcs,
        "pairs": pairs,
        "auxiliary": auxiliary,
    }
