"""Protocol factory and compatibility validation for EMS asset configs."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Set

from .base_transport import ProtocolDescriptor


JsonDict = Dict[str, Any]


class ProtocolFactory:
    """
    Build protocol descriptors from asset config.

    Real connections remain in the existing drivers/services, but this
    factory gives the codebase one shared place to reason about protocols.
    """

    LEGACY_ACTIVE_SUPPORT: Dict[str, Set[str]] = {
        "pcs": {"modbus_tcp"},
        "bms": {"modbus_tcp"},
        "chiller": {"modbus_rtu", "mock"},
    }

    KNOWN_PROTOCOLS: Set[str] = {"modbus_tcp", "modbus_rtu", "can", "mock"}

    @classmethod
    def create(
        cls,
        *,
        asset_type: str,
        protocol: Optional[str],
        connection: Optional[Mapping[str, Any]] = None,
        profile: Optional[str] = None,
        vendor: Optional[str] = None,
    ) -> ProtocolDescriptor:
        descriptor = ProtocolDescriptor.from_mapping(
            protocol=protocol,
            connection=connection,
            profile=profile,
            vendor=vendor,
        )
        return descriptor

    @classmethod
    def is_known_protocol(cls, protocol: str) -> bool:
        return ProtocolDescriptor.normalize_protocol(protocol) in cls.KNOWN_PROTOCOLS

    @classmethod
    def is_supported_by_legacy_service(cls, asset_type: str, protocol: str) -> bool:
        normalized_type = str(asset_type or "").strip().lower()
        normalized_protocol = ProtocolDescriptor.normalize_protocol(protocol)
        return normalized_protocol in cls.LEGACY_ACTIVE_SUPPORT.get(normalized_type, set())

    @classmethod
    def compatibility_status(cls, *, asset_type: str, protocol: str) -> JsonDict:
        normalized_type = str(asset_type or "").strip().lower()
        normalized_protocol = ProtocolDescriptor.normalize_protocol(protocol)
        return {
            "asset_type": normalized_type,
            "protocol": normalized_protocol,
            "known_protocol": cls.is_known_protocol(normalized_protocol),
            "legacy_service_supported": cls.is_supported_by_legacy_service(
                normalized_type,
                normalized_protocol,
            ),
            "legacy_supported_protocols": sorted(cls.LEGACY_ACTIVE_SUPPORT.get(normalized_type, set())),
            "note": (
                "active in current legacy service path"
                if cls.is_supported_by_legacy_service(normalized_type, normalized_protocol)
                else "descriptor/config supported; active service integration still required for this asset/protocol"
            ),
        }
