"""
Command classification helpers.

These helpers preserve the existing command routing rules from main.py while
pulling routing knowledge into a small, testable module. Future assets can add
new command classifiers without expanding main.py.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Set


JsonDict = Dict[str, Any]


DEFAULT_BMS_COMMANDS: Set[str] = {
    "READ_BMS",
    "READ_BMS_ALL",
    "READ_BMS_ALARMS",
    "START_BMS_PRECHARGE",
    "STOP_BMS_PRECHARGE",
    "START_BMS_INSULATION_TEST",
    "START_INSULATION_TEST",
    "RESET_BCU",
    "RESET_BMS",
}


DEFAULT_PCS_READ_COMMANDS: Set[str] = {
    "PCS_READ",
    "READ_PCS",
    "PCS_STATUS",
}


def normalize_command(command_packet: JsonDict) -> str:
    return str(command_packet.get("command", "")).strip().upper()


def _normalized_set(values: Iterable[Any]) -> Set[str]:
    return {str(value).strip().upper() for value in values if str(value).strip()}


def _packet_targets_asset(command_packet: JsonDict, asset_type: str, asset_id: str) -> bool:
    requested_type = str(command_packet.get("asset_type", "")).strip().lower()
    requested_id = str(command_packet.get("asset_id", "")).strip().lower()
    return requested_type == asset_type.lower() or (
        bool(asset_id) and requested_id == str(asset_id).strip().lower()
    )


def is_bms_command(
    command_packet: JsonDict,
    bms_asset_id: str = "bms_1",
    configured_bms_commands: Iterable[Any] = (),
) -> bool:
    command = normalize_command(command_packet)
    configured = _normalized_set(configured_bms_commands)

    return (
        command in configured
        or command.startswith("BMS_")
        or command in DEFAULT_BMS_COMMANDS
        or _packet_targets_asset(command_packet, "bms", bms_asset_id)
    )


def is_pcs_command(command_packet: JsonDict, pcs_asset_id: str = "pcs_1") -> bool:
    command = normalize_command(command_packet)

    return (
        command.startswith("PCS_")
        or command in DEFAULT_PCS_READ_COMMANDS
        or _packet_targets_asset(command_packet, "pcs", pcs_asset_id)
    )
