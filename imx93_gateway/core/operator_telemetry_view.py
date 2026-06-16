"""Operator-facing telemetry filtering utilities.

The gateway keeps full engineering telemetry for diagnostics, logging, and
support tools. Operator dashboard grids usually need a cleaner view with raw
registers, storage paths, and internal debug fields removed.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

JsonDict = Dict[str, Any]

# Exact keys that are useful for diagnostics but add noise in operator grids.
EXACT_HIDDEN_KEYS = {
    "storage_logger",
    "raw_telemetry_registers",
    "raw_registers",
    "register_map",
    "debug",
    "internal",
    "diagnostics",
    "raw_log_response",
    "settings_registers_200_to_208",
    "fault_binary",
    "fault_active_bits",
    "control_mode_raw",
    "on_off_raw",
    "on_off_status_raw",
    "set_temperature_raw",
}

# Substrings that identify engineering/debug fields. Keep these conservative so
# normal operator values such as fault_code, fault_active, and control_mode stay
# visible.
HIDDEN_KEY_SUBSTRINGS = (
    "raw_telemetry",
    "raw_register",
    "registers_",
    "_registers",
    "register_block",
    "storage_logger",
    "logger_",
    "_logger",
    "debug",
    "internal",
    "binary",
    "active_bits",
)

# Top-level metadata that can remain visible in operator API responses.
ALLOWED_TOP_LEVEL_KEYS = {
    "type",
    "status",
    "gateway_id",
    "asset_id",
    "asset_type",
    "timestamp",
    "last_poll_time",
    "online",
    "message",
    "data",
    "telemetry",
    "assets",
    "pcs",
    "bms",
    "chiller",
}


def should_hide_operator_key(key: str) -> bool:
    """Return True when a key is noisy for an operator telemetry grid."""

    key_text = str(key or "")
    key_lower = key_text.lower()

    if key_text in EXACT_HIDDEN_KEYS or key_lower in EXACT_HIDDEN_KEYS:
        return True

    if key_lower.startswith("raw_") or key_lower.endswith("_raw"):
        return True

    return any(pattern in key_lower for pattern in HIDDEN_KEY_SUBSTRINGS)


def filter_operator_telemetry(value: Any, *, _top_level: bool = False) -> Any:
    """Recursively remove noisy fields from telemetry.

    Lists of scalars are preserved unless their parent key is hidden. Dictionaries
    are filtered recursively. Empty dictionaries that result from filtering are
    omitted by the parent caller.
    """

    if isinstance(value, list):
        return [filter_operator_telemetry(item) for item in value]

    if not isinstance(value, dict):
        return value

    output: JsonDict = {}
    for key, child in value.items():
        key_text = str(key)

        # At the outermost response, preserve common metadata keys even if the
        # value is a nested object. Noisy child fields are still filtered below.
        if not _top_level or key_text not in ALLOWED_TOP_LEVEL_KEYS:
            if should_hide_operator_key(key_text):
                continue

        filtered_child = filter_operator_telemetry(child)
        if isinstance(filtered_child, dict) and not filtered_child:
            continue
        output[key_text] = filtered_child

    return output


def make_operator_response(full_response: JsonDict) -> JsonDict:
    """Create an operator-friendly copy of a full telemetry response."""

    if not isinstance(full_response, dict):
        return {"status": "error", "message": "Telemetry response must be a dictionary"}

    filtered = filter_operator_telemetry(deepcopy(full_response), _top_level=True)
    if isinstance(filtered, dict):
        filtered.setdefault("view", "operator")
    return filtered
