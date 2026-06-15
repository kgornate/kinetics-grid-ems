"""Chiller asset adapter."""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.asset_registry import AssetDescriptor
from .base_asset import BaseAssetAdapter, JsonDict


class ChillerAssetAdapter(BaseAssetAdapter):
    """
    Adapter for both real chiller service and mock chiller service.

    It preserves the existing chiller telemetry and command response shapes by
    delegating directly to `get_telemetry_packet()` and `execute_command()`.
    """

    def __init__(self, descriptor: AssetDescriptor, service: Any, mode: str = "real"):
        super().__init__(descriptor=descriptor, service=service)
        self.mode = mode

    def start(self) -> None:
        if hasattr(self.service, "start_polling"):
            self.service.start_polling()

    def stop(self) -> None:
        if hasattr(self.service, "stop_polling"):
            self.service.stop_polling()

    def get_telemetry(self) -> JsonDict:
        return self.service.get_telemetry_packet()

    def get_state(self) -> Optional[JsonDict]:
        if hasattr(self.service, "get_latest_state_dict"):
            return self.service.get_latest_state_dict()
        if hasattr(self.service, "mock_state"):
            return dict(getattr(self.service, "mock_state"))
        return None

    def execute_command(self, command_packet: Dict[str, Any]) -> JsonDict:
        return self.service.execute_command(command_packet)

    def get_status(self) -> JsonDict:
        status = super().get_status()
        status["mode"] = self.mode
        return status
