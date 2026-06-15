"""BMS profile package.

BMS profiles align with the existing PCS profile pattern. The active
legacy BMS driver still imports drivers/bms_register_map.py, but this package
provides the profile location where future real-vendor BMS mappings can be
added without touching gateway/core code.
"""

from .simulator_modbus_tcp_profile import PROFILE_NAME, PROFILE_VENDOR, PROFILE_PROTOCOL

__all__ = ["PROFILE_NAME", "PROFILE_VENDOR", "PROFILE_PROTOCOL"]
