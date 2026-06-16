"""Runtime asset catalog utilities.

The catalog merges configured assets, active runtime status, and latest telemetry
into one asset-indexed view. It lets APIs become asset-list driven while keeping
current fixed chiller/PCS/BMS services compatible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

JsonDict = Dict[str, Any]


_ASSET_ALIASES = {
    "chiller": "chiller",
    "chiller_1": "chiller",
    "pcs": "pcs",
    "pcs_1": "pcs",
    "inverter": "pcs",
    "inverter_1": "pcs",
    "bms": "bms",
    "bms_1": "bms",
    "bcu": "bms",
    "bcu_1": "bms",
}

_LEGACY_PROTOCOLS = {
    "chiller": "modbus_rtu",
    "pcs": "modbus_tcp",
    "bms": "modbus_tcp",
}


@dataclass
class RuntimeAssetRecord:
    """One asset as seen by runtime APIs."""

    asset_id: str
    asset_key: str
    asset_type: str
    enabled: bool = False
    running: bool = False
    online: bool = False
    protocol: Optional[str] = None
    profile: Optional[str] = None
    vendor: Optional[str] = None
    configured: bool = False
    telemetry_available: bool = False
    runtime_mode: str = "configured_only"
    compatibility: JsonDict = field(default_factory=dict)
    connection: JsonDict = field(default_factory=dict)
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return {
            "asset_id": self.asset_id,
            "asset_key": self.asset_key,
            "asset_type": self.asset_type,
            "enabled": self.enabled,
            "running": self.running,
            "online": self.online,
            "protocol": self.protocol,
            "profile": self.profile,
            "vendor": self.vendor,
            "configured": self.configured,
            "telemetry_available": self.telemetry_available,
            "runtime_mode": self.runtime_mode,
            "compatibility": self.compatibility,
            "connection": self.connection,
            "metadata": self.metadata,
        }


class RuntimeAssetCatalog:
    """Build an asset catalog from gateway status and telemetry."""

    def __init__(self, records: Iterable[RuntimeAssetRecord]):
        self.records: List[RuntimeAssetRecord] = list(records)
        self._by_id = {record.asset_id.lower(): record for record in self.records}
        self._by_key = {record.asset_key.lower(): record for record in self.records}

    @staticmethod
    def normalize_asset_key(asset_id: str) -> str:
        text = str(asset_id or "").strip().lower()
        return _ASSET_ALIASES.get(text, text)

    @classmethod
    def from_packets(cls, *, status_packet: Optional[JsonDict], telemetry_packet: Optional[JsonDict]) -> "RuntimeAssetCatalog":
        status_packet = status_packet if isinstance(status_packet, dict) else {}
        telemetry_packet = telemetry_packet if isinstance(telemetry_packet, dict) else {}

        records: Dict[str, RuntimeAssetRecord] = {}

        # Configured asset-list entries, if present.
        configured = status_packet.get("configured_assets", {})
        configured_assets = configured.get("assets", []) if isinstance(configured, dict) else []
        if isinstance(configured_assets, list):
            for item in configured_assets:
                if not isinstance(item, dict):
                    continue
                record = cls._record_from_config(item, status_packet, telemetry_packet)
                records[record.asset_id.lower()] = record

        # Compatibility sections for the current active services. These ensure
        # old configs without an assets[] list still produce the expected assets.
        for asset_key in ("chiller", "pcs", "bms"):
            section = status_packet.get(asset_key, {})
            if not isinstance(section, dict):
                section = {}
            asset_id = str(section.get("asset_id") or cls._default_asset_id(asset_key))
            _, packet = cls.extract_asset_packet(asset_id, telemetry_packet)
            existing = records.get(asset_id.lower())
            record = cls._record_from_status(asset_key, section, packet, existing)
            records[asset_id.lower()] = record

        return cls(records.values())

    @classmethod
    def _record_from_config(cls, item: JsonDict, status_packet: JsonDict, telemetry_packet: JsonDict) -> RuntimeAssetRecord:
        asset_id = str(item.get("asset_id") or item.get("id") or "unknown_asset")
        asset_key = str(item.get("asset_key") or cls.normalize_asset_key(asset_id))
        asset_type = str(item.get("asset_type") or asset_key)
        _, packet = cls.extract_asset_packet(asset_id, telemetry_packet)
        section = status_packet.get(asset_key, {}) if isinstance(status_packet.get(asset_key), dict) else {}
        enabled = bool(item.get("enabled", section.get("enabled", False)))
        running = bool(section.get("running", False))
        online = cls.is_asset_online(asset_key, packet, status_packet)
        compatibility = item.get("compatibility") if isinstance(item.get("compatibility"), dict) else {}
        legacy_supported = bool(compatibility.get("legacy_service_supported", False))
        runtime_mode = "active_service" if running else ("disabled" if not enabled else "configured_only")
        if enabled and not running and not legacy_supported:
            runtime_mode = "configured_future"
        return RuntimeAssetRecord(
            asset_id=asset_id,
            asset_key=asset_key,
            asset_type=asset_type,
            enabled=enabled,
            running=running,
            online=online,
            protocol=item.get("protocol") or section.get("protocol"),
            profile=item.get("profile") or section.get("profile"),
            vendor=item.get("vendor") or section.get("vendor"),
            configured=True,
            telemetry_available=packet is not None,
            runtime_mode=runtime_mode,
            compatibility=compatibility,
            connection=cls._connection_from_item(item, section),
            metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
        )

    @classmethod
    def _record_from_status(
        cls,
        asset_key: str,
        section: JsonDict,
        packet: Optional[JsonDict],
        existing: Optional[RuntimeAssetRecord] = None,
    ) -> RuntimeAssetRecord:
        asset_id = str(section.get("asset_id") or (existing.asset_id if existing else cls._default_asset_id(asset_key)))
        enabled = bool(section.get("enabled", existing.enabled if existing else packet is not None))
        running = bool(section.get("running", existing.running if existing else packet is not None))
        online = cls.is_asset_online(asset_key, packet, {asset_key: section})
        runtime_mode = "active_service" if running else ("disabled" if not enabled else "configured_only")
        return RuntimeAssetRecord(
            asset_id=asset_id,
            asset_key=asset_key,
            asset_type=str(section.get("asset_type") or (existing.asset_type if existing else asset_key)),
            enabled=enabled,
            running=running,
            online=online,
            protocol=section.get("protocol") or (existing.protocol if existing else _LEGACY_PROTOCOLS.get(asset_key)),
            profile=section.get("profile") or (existing.profile if existing else None),
            vendor=section.get("vendor") or (existing.vendor if existing else None),
            configured=bool(existing.configured if existing else False),
            telemetry_available=packet is not None,
            runtime_mode=runtime_mode,
            compatibility=existing.compatibility if existing else {},
            connection=cls._connection_from_item(existing.to_dict() if existing else {}, section),
            metadata=existing.metadata if existing else {},
        )

    @staticmethod
    def _default_asset_id(asset_key: str) -> str:
        if asset_key == "pcs":
            return "pcs_1"
        if asset_key == "bms":
            return "bms_1"
        if asset_key == "chiller":
            return "chiller_1"
        return asset_key

    @staticmethod
    def _connection_from_item(item: JsonDict, section: JsonDict) -> JsonDict:
        connection = item.get("connection") if isinstance(item.get("connection"), dict) else {}
        out: JsonDict = dict(connection)
        for key in ["host", "port", "unit_id", "serial_port", "baudrate", "protocol"]:
            if section.get(key) is not None and key not in out:
                out[key] = section.get(key)
        return out

    @classmethod
    def extract_asset_packet(cls, asset_id: str, telemetry_packet: Optional[JsonDict]) -> Tuple[str, Optional[JsonDict]]:
        asset_key = cls.normalize_asset_key(asset_id)
        telemetry_packet = telemetry_packet if isinstance(telemetry_packet, dict) else {}
        assets = telemetry_packet.get("assets", {}) if isinstance(telemetry_packet.get("assets"), dict) else {}

        for candidate in (asset_id, asset_key):
            packet = assets.get(candidate)
            if isinstance(packet, dict):
                return asset_key, packet

        if asset_key in {"pcs", "bms"} and isinstance(telemetry_packet.get(asset_key), dict):
            return asset_key, telemetry_packet.get(asset_key)

        if asset_key == "chiller":
            if str(telemetry_packet.get("asset_id", "")).lower() in {"chiller", "chiller_1"}:
                return asset_key, telemetry_packet
            packet = assets.get("chiller")
            if isinstance(packet, dict):
                return asset_key, packet

        return asset_key, None

    @staticmethod
    def is_asset_online(asset_key: str, asset_packet: Optional[JsonDict], status_packet: Optional[JsonDict]) -> bool:
        if not asset_packet:
            return False

        status_texts: List[str] = []
        for key in ["status", "communication_status", "comm_status", "modbus_status"]:
            value = asset_packet.get(key)
            if value is not None:
                status_texts.append(str(value).lower())
        data = asset_packet.get("data")
        if isinstance(data, dict):
            for key in ["communication_status", "comm_status", "modbus_status"]:
                value = data.get(key)
                if value is not None:
                    status_texts.append(str(value).lower())

        if any(text in {"offline", "error", "lost", "failed"} for text in status_texts):
            return False
        if any(text in {"online", "ok", "connected", "success", "healthy", "mock"} for text in status_texts):
            return True

        if status_packet and isinstance(status_packet.get(asset_key), dict):
            return bool(status_packet[asset_key].get("running"))
        return True

    def find(self, asset_id: str) -> Optional[RuntimeAssetRecord]:
        text = str(asset_id or "").strip().lower()
        return self._by_id.get(text) or self._by_key.get(text) or self._by_key.get(self.normalize_asset_key(text))

    def to_response(self, *, gateway_id: Optional[str], timestamp: str) -> JsonDict:
        assets = [record.to_dict() for record in self.records]
        return {
            "status": "ok",
            "gateway_id": gateway_id,
            "timestamp": timestamp,
            "assets_count": len(assets),
            "assets": assets,
            "summary": self.summary(),
        }

    def summary(self) -> JsonDict:
        out = {"total": len(self.records), "enabled": 0, "running": 0, "online": 0, "configured_only": 0, "configured_future": 0, "disabled": 0}
        for record in self.records:
            if record.enabled:
                out["enabled"] += 1
            if record.running:
                out["running"] += 1
            if record.online:
                out["online"] += 1
            if record.runtime_mode in out:
                out[record.runtime_mode] += 1
        return out
