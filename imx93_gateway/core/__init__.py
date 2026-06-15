"""
Core compatibility layer for the EMS gateway.

This package introduces modular asset registration, asset adapters, command
classification, and telemetry composition without changing the existing
UDP/TCP/HTTP/Web API contracts used by Flutter and the web dashboard.
"""

from .asset_registry import AssetDescriptor, AssetRegistry
from .assets import BaseAssetAdapter, BmsAssetAdapter, ChillerAssetAdapter, PcsAssetAdapter
from .command_router import is_bms_command, is_pcs_command, normalize_command
from .command_dispatcher import CommandDispatcher
from .telemetry_composer import compose_legacy_udp_packet

__all__ = [
    "AssetDescriptor",
    "AssetRegistry",
    "BaseAssetAdapter",
    "BmsAssetAdapter",
    "ChillerAssetAdapter",
    "PcsAssetAdapter",
    "compose_legacy_udp_packet",
    "CommandDispatcher",
    "is_bms_command",
    "is_pcs_command",
    "normalize_command",
]
