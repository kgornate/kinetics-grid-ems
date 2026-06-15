"""
Unified command dispatcher for the EMS gateway.

Design goal:
- Move gateway/asset command routing out of main.py.
- Preserve every external TCP/Web API command contract used by Flutter and the
  web dashboard.
- Keep existing service adapters as the command execution layer.

This dispatcher is intentionally compatibility-first. It does not rewrite
Modbus operations and it does not change response JSON shapes.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Mapping, Optional

from core.command_router import is_bms_command, is_pcs_command, normalize_command
from core.response_utils import command_response


JsonDict = Dict[str, Any]
AdapterGetter = Callable[[str], Optional[Any]]
PacketCallback = Callable[[], JsonDict]
ConfigCommandsProvider = Callable[[], Iterable[Any]]
LegacyHandler = Callable[[JsonDict], JsonDict]


class CommandDispatcher:
    """Route gateway command packets to the correct command executor."""

    GATEWAY_STATUS_COMMANDS = {"GATEWAY_STATUS", "STATUS"}
    GATEWAY_TELEMETRY_COMMANDS = {"READ_ALL_ASSETS", "READ_GATEWAY_TELEMETRY"}

    def __init__(
        self,
        *,
        gateway_id: str,
        get_asset_adapter: AdapterGetter,
        get_status_packet: PacketCallback,
        get_telemetry_packet: PacketCallback,
        bms_asset_id: str = "bms_1",
        pcs_asset_id: str = "pcs_1",
        configured_bms_commands_provider: Optional[ConfigCommandsProvider] = None,
        legacy_asset_handlers: Optional[Mapping[str, LegacyHandler]] = None,
        default_asset_key: str = "chiller",
    ):
        self.gateway_id = gateway_id
        self.get_asset_adapter = get_asset_adapter
        self.get_status_packet = get_status_packet
        self.get_telemetry_packet = get_telemetry_packet
        self.bms_asset_id = bms_asset_id
        self.pcs_asset_id = pcs_asset_id
        self.configured_bms_commands_provider = configured_bms_commands_provider or (lambda: set())
        self.legacy_asset_handlers = dict(legacy_asset_handlers or {})
        self.default_asset_key = default_asset_key

    def dispatch(self, command_packet: JsonDict) -> JsonDict:
        """
        Dispatch one command packet and return a gateway response.

        Compatibility notes:
        - Missing command returns the same error shape used by main.py earlier.
        - STATUS/GATEWAY_STATUS and READ_ALL_ASSETS/READ_GATEWAY_TELEMETRY keep
          the same messages and payload keys.
        - PCS/BMS classification uses the same helpers introduced in Core.
        - Chiller remains the default route for legacy Flutter commands such as
          READ_ALL, SET_TEMP, CHILLER_ON, etc.
        """
        if not isinstance(command_packet, dict):
            command_packet = {}

        request_id = command_packet.get("request_id")
        command = normalize_command(command_packet)

        if not command:
            return self._response(
                request_id=request_id,
                command=command,
                status="error",
                message="Missing command",
            )

        route = self.route(command_packet)

        if route == "gateway_status":
            return self._response(
                request_id=request_id,
                command=command,
                status="ok",
                message="Gateway status read successfully",
                data=self.get_status_packet(),
            )

        if route == "gateway_telemetry":
            return self._response(
                request_id=request_id,
                command=command,
                status="ok",
                message="Combined telemetry read successfully",
                data=self.get_telemetry_packet(),
            )

        if route in {"bms", "pcs", "chiller"}:
            return self._dispatch_asset(route, command_packet, request_id, command)

        return self._response(
            request_id=request_id,
            command=command,
            status="error",
            message=f"No route available for command: {command}",
        )

    def route(self, command_packet: JsonDict) -> str:
        """Return the logical route key for a command packet."""
        command = normalize_command(command_packet)

        if command in self.GATEWAY_STATUS_COMMANDS:
            return "gateway_status"

        if command in self.GATEWAY_TELEMETRY_COMMANDS:
            return "gateway_telemetry"

        configured_bms_commands = self.configured_bms_commands_provider()
        if is_bms_command(
            command_packet,
            bms_asset_id=self.bms_asset_id,
            configured_bms_commands=configured_bms_commands,
        ):
            return "bms"

        if is_pcs_command(command_packet, pcs_asset_id=self.pcs_asset_id):
            return "pcs"

        return self.default_asset_key

    def _dispatch_asset(
        self,
        asset_key: str,
        command_packet: JsonDict,
        request_id: Optional[Any],
        command: str,
    ) -> JsonDict:
        adapter = self.get_asset_adapter(asset_key)
        if adapter is not None:
            try:
                return adapter.execute_command(command_packet)
            except Exception as error:
                return self._response(
                    request_id=request_id,
                    command=command,
                    status="error",
                    message=str(error),
                )

        legacy_handler = self.legacy_asset_handlers.get(asset_key)
        if legacy_handler is not None:
            return legacy_handler(command_packet)

        if asset_key == "bms":
            message = "BMS service is not running"
        elif asset_key == "pcs":
            message = "PCS service is not running"
        else:
            message = f"No service available to handle command: {command}"

        return self._response(
            request_id=request_id,
            command=command,
            status="error",
            message=message,
        )

    def get_status(self) -> JsonDict:
        """Return additive dispatcher diagnostics safe to expose in status."""
        return {
            "dispatcher_class": self.__class__.__name__,
            "gateway_id": self.gateway_id,
            "gateway_status_commands": sorted(self.GATEWAY_STATUS_COMMANDS),
            "gateway_telemetry_commands": sorted(self.GATEWAY_TELEMETRY_COMMANDS),
            "default_asset_key": self.default_asset_key,
            "pcs_asset_id": self.pcs_asset_id,
            "bms_asset_id": self.bms_asset_id,
            "legacy_fallbacks": sorted(self.legacy_asset_handlers.keys()),
        }

    @staticmethod
    def _response(
        *,
        request_id: Optional[Any],
        command: str,
        status: str,
        message: str,
        data: Optional[JsonDict] = None,
    ) -> JsonDict:
        return command_response(
            request_id=request_id,
            command=command,
            status=status,
            message=message,
            data=data,
        )
