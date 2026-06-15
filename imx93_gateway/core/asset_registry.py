"""
Asset registry for gateway runtime services.

Design intent:
- Keep the current chiller/PCS/BMS services unchanged.
- Provide one small place where currently running assets are described.
- Make future assets pluggable without forcing every network/API layer to know
  the concrete service class.

This is a compatibility layer, not a rewrite. Existing main.py service startup,
UDP telemetry shape, TCP command routes, HTTP logs, and Web API callbacks remain
valid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional


JsonDict = Dict[str, Any]


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class AssetDescriptor:
    """Runtime description of one physical/logical EMS asset."""

    asset_key: str
    asset_id: str
    asset_type: str
    enabled: bool = True
    service: Optional[Any] = None
    transport: str = "unknown"
    vendor: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    unit_id: Optional[int] = None
    metadata: JsonDict = field(default_factory=dict)
    registered_at: str = field(default_factory=_now)

    @property
    def running(self) -> bool:
        return self.service is not None

    def to_status(self) -> JsonDict:
        """Return an additive status object safe to expose through /status."""
        return {
            "asset_key": self.asset_key,
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "enabled": self.enabled,
            "running": self.running,
            "transport": self.transport,
            "vendor": self.vendor,
            "host": self.host,
            "port": self.port,
            "unit_id": self.unit_id,
            "registered_at": self.registered_at,
            "metadata": dict(self.metadata or {}),
        }


class AssetRegistry:
    """
    Thread-safe registry of runtime asset descriptors.

    Network layers should eventually depend on this registry instead of concrete
    variables such as self.pcs_service and self.bms_service. The registry stays beside the existing variables so behavior stays unchanged.
    """

    def __init__(self, gateway_id: str):
        self.gateway_id = gateway_id
        self._assets: Dict[str, AssetDescriptor] = {}
        self._lock = RLock()

    @staticmethod
    def normalize_key(asset_key: str) -> str:
        key = str(asset_key or "").strip().lower()
        aliases = {
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
        return aliases.get(key, key)

    def register(self, descriptor: AssetDescriptor) -> None:
        key = self.normalize_key(descriptor.asset_key)
        descriptor.asset_key = key
        with self._lock:
            self._assets[key] = descriptor

    def unregister(self, asset_key: str) -> None:
        key = self.normalize_key(asset_key)
        with self._lock:
            self._assets.pop(key, None)

    def get(self, asset_key: str) -> Optional[AssetDescriptor]:
        key = self.normalize_key(asset_key)
        with self._lock:
            return self._assets.get(key)

    def values(self) -> List[AssetDescriptor]:
        with self._lock:
            return list(self._assets.values())

    def keys(self) -> List[str]:
        with self._lock:
            return list(self._assets.keys())

    def is_registered(self, asset_key: str) -> bool:
        return self.get(asset_key) is not None

    def to_status_list(self) -> List[JsonDict]:
        return [asset.to_status() for asset in self.values()]

    def to_status_map(self) -> Dict[str, JsonDict]:
        with self._lock:
            return {key: asset.to_status() for key, asset in self._assets.items()}

    def summary(self) -> JsonDict:
        assets = self.to_status_map()
        return {
            "gateway_id": self.gateway_id,
            "asset_count": len(assets),
            "asset_keys": list(assets.keys()),
            "assets": assets,
        }

    def find_by_asset_id(self, asset_id: str) -> Optional[AssetDescriptor]:
        normalized = str(asset_id or "").strip().lower()
        if not normalized:
            return None
        with self._lock:
            for asset in self._assets.values():
                if str(asset.asset_id).lower() == normalized:
                    return asset
        return None

    def extend(self, descriptors: Iterable[AssetDescriptor]) -> None:
        for descriptor in descriptors:
            self.register(descriptor)
