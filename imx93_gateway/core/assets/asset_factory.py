"""
Asset factory helpers.

The current gateway still starts the existing chiller/PCS/BMS services in
main.py for compatibility. This factory is intentionally lightweight: it turns
configured asset definitions into startup/compatibility plans so future assets
can be added without spreading protocol/vendor rules through main.py.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .asset_profile import AssetProfileDefinition


JsonDict = Dict[str, Any]


class AssetFactoryPlan:
    """Read-only plan describing how configured assets map to legacy services."""

    def __init__(self, definitions: Iterable[AssetProfileDefinition]):
        self.definitions = list(definitions)

    def to_status(self) -> JsonDict:
        return {
            "factory_class": self.__class__.__name__,
            "asset_count": len(self.definitions),
            "assets": [definition.to_status() for definition in self.definitions],
        }

    def unsupported_active_protocols(self) -> List[JsonDict]:
        unsupported: List[JsonDict] = []
        for definition in self.definitions:
            status = definition.compatibility_status()
            if definition.enabled and not status.get("legacy_service_supported", False):
                unsupported.append(status)
        return unsupported
