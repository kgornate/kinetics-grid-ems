"""BMS / BCU asset adapter."""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.asset_registry import AssetDescriptor
from .base_asset import BaseAssetAdapter, JsonDict


class BmsAssetAdapter(BaseAssetAdapter):
    """
    Adapter around the existing BmsGatewayService.

    It preserves the previous BMS command behavior: the gateway passes only the
    normalized command string into BmsGatewayService.execute_command().
    """

    def __init__(self, descriptor: AssetDescriptor, service: Any):
        super().__init__(descriptor=descriptor, service=service)

    def start(self) -> None:
        if hasattr(self.service, "start"):
            self.service.start()

    def stop(self) -> None:
        if hasattr(self.service, "stop"):
            self.service.stop()

    def get_telemetry(self) -> JsonDict:
        return self.service.get_telemetry_payload()

    def get_state(self) -> Optional[JsonDict]:
        return self.service.get_latest_state_dict()

    def execute_command(self, command_packet: Dict[str, Any]) -> JsonDict:
        request_id = command_packet.get("request_id")
        command = str(command_packet.get("command", "")).strip().upper()

        try:
            result = self.service.execute_command(command)
            return self._bms_command_response(request_id, command, result)
        except Exception as error:
            return self._response(
                request_id=request_id,
                command=command,
                status="error",
                message=str(error),
            )

    def _bms_command_response(
        self,
        request_id: Optional[Any],
        command: str,
        result: JsonDict,
    ) -> JsonDict:
        bms_status = str(result.get("status", "")).lower()
        response_status = "ok" if bms_status in {"success", "ok"} else "error"

        return self._response(
            request_id=request_id,
            command=command,
            status=response_status,
            message=result.get("message", result.get("description", "BMS command executed")),
            data=result,
        )
