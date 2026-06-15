"""
Asset profile/config definitions for the EMS gateway.

Design goal:
- Allow deployments to describe assets as an `assets: [...]` list in JSON.
- Keep existing flat config.py / CLI fields working.
- Make IP/port/unit/vendor/profile/protocol changes config-driven for current
  Modbus TCP PCS/BMS and Modbus RTU chiller paths.
- Provide a clean place to add future BMS/PCS/CAN/RTU profiles without
  rewriting main.py, Flutter, or web dashboard contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional

from core.protocols import ProtocolDescriptor, ProtocolFactory


JsonDict = Dict[str, Any]


_KEY_ALIASES = {
    "id": "asset_id",
    "key": "asset_key",
    "type": "asset_type",
    "asset": "asset_type",
    "enabled": "enabled",
    "vendor": "vendor",
    "protocol": "protocol",
    "profile": "profile",
    "connection": "connection",
    "poll_interval": "poll_interval_sec",
    "poll_interval_seconds": "poll_interval_sec",
    "timeout": "timeout_sec",
    "timeout_seconds": "timeout_sec",
}


_ASSET_KEY_ALIASES = {
    "chiller_1": "chiller",
    "cooling": "chiller",
    "hvac": "chiller",
    "pcs_1": "pcs",
    "inverter": "pcs",
    "inverter_1": "pcs",
    "bms_1": "bms",
    "bcu": "bms",
    "bcu_1": "bms",
}


def _norm_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def normalize_asset_key(value: Any) -> str:
    text = _norm_text(value).lower().replace("-", "_").replace(" ", "_")
    return _ASSET_KEY_ALIASES.get(text, text)


def _normalize_mapping(raw: Mapping[str, Any]) -> JsonDict:
    normalized: JsonDict = {}
    for key, value in raw.items():
        norm_key = str(key).strip().lower().replace("-", "_").replace(" ", "_")
        norm_key = _KEY_ALIASES.get(norm_key, norm_key)
        normalized[norm_key] = value
    return normalized


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enabled", "enable"}:
        return True
    if text in {"0", "false", "no", "off", "disabled", "disable"}:
        return False
    return default


@dataclass(frozen=True)
class AssetProfileDefinition:
    """Deployment-time definition of one logical EMS asset."""

    asset_key: str
    asset_id: str
    asset_type: str
    enabled: bool = True
    vendor: Optional[str] = None
    protocol: str = "unknown"
    profile: Optional[str] = None
    connection: JsonDict = field(default_factory=dict)
    poll_interval_sec: Optional[float] = None
    timeout_sec: Optional[float] = None
    retries: Optional[int] = None
    metadata: JsonDict = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "AssetProfileDefinition":
        data = _normalize_mapping(raw)
        asset_type = _norm_text(data.get("asset_type"), "unknown").lower().replace("-", "_").replace(" ", "_")
        asset_id = _norm_text(data.get("asset_id"), f"{asset_type}_1")
        asset_key = normalize_asset_key(data.get("asset_key") or asset_id or asset_type)
        if not asset_key:
            asset_key = normalize_asset_key(asset_type)

        connection = dict(data.get("connection") or {})
        # Also accept flat connection fields inside one asset object.
        for source_key, target_key in [
            ("host", "host"),
            ("ip", "host"),
            ("port", "port"),
            ("unit_id", "unit_id"),
            ("slave_id", "slave_id"),
            ("serial_port", "serial_port"),
            ("baudrate", "baudrate"),
            ("parity", "parity"),
            ("stopbits", "stopbits"),
            ("bytesize", "bytesize"),
            ("interface", "interface"),
            ("bitrate", "bitrate"),
        ]:
            if source_key in data and target_key not in connection:
                connection[target_key] = data[source_key]

        metadata = dict(data.get("metadata") or {})
        for key, value in data.items():
            if key not in {
                "asset_key", "asset_id", "asset_type", "enabled", "vendor", "protocol",
                "profile", "connection", "poll_interval_sec", "timeout_sec", "retries",
                "metadata", "host", "ip", "port", "unit_id", "slave_id", "serial_port",
                "baudrate", "parity", "stopbits", "bytesize", "interface", "bitrate",
            }:
                metadata[key] = value

        return cls(
            asset_key=asset_key,
            asset_id=asset_id,
            asset_type=asset_type,
            enabled=_coerce_bool(data.get("enabled"), True),
            vendor=_norm_text(data.get("vendor")) or None,
            protocol=ProtocolDescriptor.normalize_protocol(data.get("protocol")),
            profile=_norm_text(data.get("profile")) or None,
            connection=connection,
            poll_interval_sec=float(data["poll_interval_sec"]) if data.get("poll_interval_sec") is not None else None,
            timeout_sec=float(data["timeout_sec"]) if data.get("timeout_sec") is not None else None,
            retries=int(data["retries"]) if data.get("retries") is not None else None,
            metadata=metadata,
        )

    @property
    def protocol_descriptor(self) -> ProtocolDescriptor:
        return ProtocolFactory.create(
            asset_type=self.asset_type,
            protocol=self.protocol,
            connection=self.connection,
            profile=self.profile,
            vendor=self.vendor,
        )

    def to_legacy_overrides(self) -> JsonDict:
        """
        Return flat config-style overrides for the current legacy services.

        This lets the new asset list drive the existing working code paths.
        """
        proto = self.protocol_descriptor
        overrides: JsonDict = {}
        if self.asset_type == "pcs":
            overrides["PCS_ENABLED"] = self.enabled
            overrides["PCS_ASSET_ID"] = self.asset_id
            if self.vendor:
                overrides["PCS_VENDOR"] = self.vendor
            if proto.host is not None:
                overrides["PCS_HOST"] = proto.host
            if proto.port is not None:
                overrides["PCS_PORT"] = proto.port
            if proto.unit_id is not None:
                overrides["PCS_UNIT_ID"] = proto.unit_id
            if self.poll_interval_sec is not None:
                overrides["PCS_POLL_INTERVAL_SEC"] = self.poll_interval_sec
            if self.timeout_sec is not None:
                overrides["PCS_TIMEOUT_SEC"] = self.timeout_sec
            if self.retries is not None:
                overrides["PCS_RETRIES"] = self.retries
            overrides["PCS_PROTOCOL"] = proto.protocol
            if self.profile:
                overrides["PCS_PROFILE"] = self.profile
        elif self.asset_type == "bms":
            overrides["BMS_ENABLED"] = self.enabled
            overrides["BMS_ASSET_ID"] = self.asset_id
            if self.vendor:
                overrides["BMS_VENDOR"] = self.vendor
            if proto.host is not None:
                overrides["BMS_MODBUS_HOST"] = proto.host
            if proto.port is not None:
                overrides["BMS_MODBUS_PORT"] = proto.port
            if proto.unit_id is not None:
                overrides["BMS_UNIT_ID"] = proto.unit_id
            if self.poll_interval_sec is not None:
                overrides["BMS_POLL_INTERVAL_SEC"] = self.poll_interval_sec
            if self.timeout_sec is not None:
                overrides["BMS_MODBUS_TIMEOUT_SEC"] = self.timeout_sec
            overrides["BMS_PROTOCOL"] = proto.protocol
            if self.profile:
                overrides["BMS_PROFILE"] = self.profile
        elif self.asset_type == "chiller":
            overrides["CHILLER_ENABLED"] = self.enabled
            overrides["ASSET_ID"] = self.asset_id
            if proto.serial_port is not None:
                overrides["MODBUS_PORT"] = proto.serial_port
            if proto.unit_id is not None:
                overrides["CHILLER_SLAVE_ID"] = proto.unit_id
            if "baudrate" in self.connection:
                overrides["MODBUS_BAUDRATE"] = int(self.connection["baudrate"])
            if "bytesize" in self.connection:
                overrides["MODBUS_BYTESIZE"] = int(self.connection["bytesize"])
            if "parity" in self.connection:
                overrides["MODBUS_PARITY"] = self.connection["parity"]
            if "stopbits" in self.connection:
                overrides["MODBUS_STOPBITS"] = int(self.connection["stopbits"])
            if self.poll_interval_sec is not None:
                overrides["CHILLER_POLL_INTERVAL_SEC"] = self.poll_interval_sec
            if self.timeout_sec is not None:
                overrides["MODBUS_TIMEOUT_SEC"] = self.timeout_sec
            overrides["CHILLER_PROTOCOL"] = proto.protocol
            if self.profile:
                overrides["CHILLER_PROFILE"] = self.profile
        return overrides

    def compatibility_status(self) -> JsonDict:
        return ProtocolFactory.compatibility_status(asset_type=self.asset_type, protocol=self.protocol)

    def to_status(self) -> JsonDict:
        return {
            "asset_key": self.asset_key,
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "enabled": self.enabled,
            "vendor": self.vendor,
            "protocol": self.protocol,
            "profile": self.profile,
            "connection": dict(self.connection),
            "poll_interval_sec": self.poll_interval_sec,
            "timeout_sec": self.timeout_sec,
            "retries": self.retries,
            "metadata": dict(self.metadata),
            "protocol_descriptor": self.protocol_descriptor.to_status(),
            "compatibility": self.compatibility_status(),
        }


class AssetConfigRegistry:
    """Registry of configured asset definitions loaded from runtime config."""

    def __init__(self, assets: Optional[Iterable[AssetProfileDefinition]] = None):
        self.assets: List[AssetProfileDefinition] = list(assets or [])

    @classmethod
    def from_runtime_config(cls, runtime_config: Any) -> "AssetConfigRegistry":
        raw_assets = None
        if runtime_config is not None:
            raw_assets = runtime_config.values.get("ASSETS")
        return cls.from_raw_assets(raw_assets)

    @classmethod
    def from_raw_assets(cls, raw_assets: Any) -> "AssetConfigRegistry":
        if raw_assets is None:
            return cls([])
        if isinstance(raw_assets, Mapping):
            iterable = raw_assets.values()
        elif isinstance(raw_assets, list):
            iterable = raw_assets
        else:
            raise ValueError("ASSETS config must be a list or mapping")

        definitions: List[AssetProfileDefinition] = []
        for raw in iterable:
            if not isinstance(raw, Mapping):
                raise ValueError(f"Each asset definition must be an object, got {type(raw).__name__}")
            definitions.append(AssetProfileDefinition.from_mapping(raw))
        return cls(definitions)

    def has_assets(self) -> bool:
        return bool(self.assets)

    def find(self, asset_key: Optional[str] = None, asset_type: Optional[str] = None) -> Optional[AssetProfileDefinition]:
        key = normalize_asset_key(asset_key) if asset_key else None
        atype = str(asset_type or "").strip().lower().replace("-", "_").replace(" ", "_") if asset_type else None
        for definition in self.assets:
            if key and definition.asset_key == key:
                return definition
            if atype and definition.asset_type == atype:
                return definition
        return None

    def legacy_overrides(self) -> JsonDict:
        overrides: JsonDict = {}
        for definition in self.assets:
            # Last definition for same legacy key wins, but tests/configs should
            # avoid duplicate fixed legacy assets until dynamic multi-instance
            # startup is implemented.
            overrides.update(definition.to_legacy_overrides())
        return overrides

    def to_status(self) -> JsonDict:
        return {
            "config_class": self.__class__.__name__,
            "asset_count": len(self.assets),
            "asset_keys": [asset.asset_key for asset in self.assets],
            "assets": [asset.to_status() for asset in self.assets],
            "compatibility_note": (
                "asset-list config can now drive current fixed chiller/pcs/bms services; "
                "additional dynamic multi-instance startup and non-legacy protocol activation remain future extensions"
            ),
        }
