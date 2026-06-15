"""PCS / inverter asset adapter."""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.asset_registry import AssetDescriptor
from .base_asset import BaseAssetAdapter, JsonDict


class PcsAssetAdapter(BaseAssetAdapter):
    """
    Adapter around the existing PcsGatewayService.

    The command mapping is copied from the previous main.py routing logic so
    Flutter TCP commands and web dashboard commands remain compatible.
    """

    READ_COMMANDS = {"PCS_READ", "READ_PCS", "PCS_STATUS"}

    def __init__(self, descriptor: AssetDescriptor, service: Any, vendor: str = "njoy"):
        super().__init__(descriptor=descriptor, service=service)
        self.vendor = vendor

    def start(self) -> None:
        if hasattr(self.service, "start"):
            self.service.start()

    def stop(self) -> None:
        if hasattr(self.service, "stop"):
            self.service.stop()

    def get_telemetry(self) -> JsonDict:
        return self.service.get_latest_state()

    def get_state(self) -> Optional[JsonDict]:
        return self.service.get_latest_state()

    def execute_command(self, command_packet: Dict[str, Any]) -> JsonDict:
        request_id = command_packet.get("request_id")
        command = str(command_packet.get("command", "")).strip().upper()
        value = command_packet.get("value")

        try:
            if command in self.READ_COMMANDS:
                return self._response(
                    request_id=request_id,
                    command=command,
                    status="ok",
                    message="PCS state read successfully",
                    data=self.service.get_latest_state(),
                )

            source = str(
                command_packet.get("source")
                or f"flutter_tcp_command:{command_packet.get('client', 'unknown')}"
            )

            if command == "PCS_POWER_ON":
                return self._pcs_command_response(
                    request_id,
                    command,
                    self.service.power_on(source=source),
                )

            if command == "PCS_POWER_OFF":
                return self._pcs_command_response(
                    request_id,
                    command,
                    self.service.power_off(source=source),
                )

            if command in ["PCS_STANDBY", "PCS_DEVICE_STANDBY"]:
                return self._pcs_command_response(
                    request_id,
                    command,
                    self.service.standby(source=source),
                )

            if command == "PCS_SET_ACTIVE_POWER":
                if value is None:
                    value = command_packet.get("kw", command_packet.get("active_power_kw"))

                if value is None:
                    return self._response(
                        request_id=request_id,
                        command=command,
                        status="error",
                        message="PCS_SET_ACTIVE_POWER requires value / kw / active_power_kw",
                    )

                return self._pcs_command_response(
                    request_id,
                    command,
                    self.service.set_active_power_kw(float(value), source=source),
                )

            if command == "PCS_SET_REACTIVE_POWER":
                if value is None:
                    value = command_packet.get("kvar", command_packet.get("reactive_power_kvar"))

                if value is None:
                    return self._response(
                        request_id=request_id,
                        command=command,
                        status="error",
                        message="PCS_SET_REACTIVE_POWER requires value / kvar / reactive_power_kvar",
                    )

                return self._pcs_command_response(
                    request_id,
                    command,
                    self.service.set_reactive_power_kvar(float(value), source=source),
                )

            if command == "PCS_RESET_FAULT":
                return self._pcs_command_response(
                    request_id,
                    command,
                    self.service.reset_fault(source=source),
                )

            if command == "PCS_HEARTBEAT":
                return self._pcs_command_response(
                    request_id,
                    command,
                    self.service.heartbeat(value=value, source=source),
                )

            return self._response(
                request_id=request_id,
                command=command,
                status="error",
                message=f"Unsupported PCS command: {command}",
            )

        except Exception as error:
            return self._response(
                request_id=request_id,
                command=command,
                status="error",
                message=str(error),
            )

    def _pcs_command_response(
        self,
        request_id: Optional[Any],
        command: str,
        result: JsonDict,
    ) -> JsonDict:
        pcs_status = str(result.get("status", "")).lower()
        response_status = "ok" if pcs_status in {"success", "ok"} else "error"

        return self._response(
            request_id=request_id,
            command=command,
            status=response_status,
            message=result.get("description", "PCS command executed"),
            data=result,
        )

    def get_status(self) -> JsonDict:
        status = super().get_status()
        status["vendor"] = self.vendor
        return status
