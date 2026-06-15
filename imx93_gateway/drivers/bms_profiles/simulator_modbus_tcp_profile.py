"""Current BMS simulator / default Modbus TCP profile descriptor.

The existing BMS implementation stores its register map and decode helpers in
`drivers.bms_register_map`. This file does not duplicate that logic. It gives
a profile name and stable import path, similar to PCS profiles.
"""

from __future__ import annotations

from typing import Any, Dict

from drivers import bms_register_map as register_map

PROFILE_NAME = "simulator_modbus_tcp"
PROFILE_VENDOR = "simulator"
PROFILE_PROTOCOL = "modbus_tcp"


def get_profile_status() -> Dict[str, Any]:
    return {
        "profile_name": PROFILE_NAME,
        "vendor": PROFILE_VENDOR,
        "protocol": PROFILE_PROTOCOL,
        "register_map_module": "drivers.bms_register_map",
        "has_read_blocks": hasattr(register_map, "READ_BLOCKS"),
        "has_control_registers": hasattr(register_map, "CONTROL_REGISTERS"),
        "note": "Descriptor around the current legacy BMS register map.",
    }
