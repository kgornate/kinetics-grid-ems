"""
Common asset adapter contract for the EMS gateway.

Design goal:
- Give every asset a common software interface.
- Keep existing chiller/PCS/BMS services and drivers unchanged.
- Preserve UDP/TCP/HTTP/Web API behavior while reducing direct application coupling.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from core.asset_registry import AssetDescriptor
from core.response_utils import command_response


JsonDict = Dict[str, Any]


class BaseAssetAdapter(ABC):
    """
    Thin compatibility adapter around an existing asset service.

    The adapter does not own protocol details. It delegates to the existing
    service/driver methods and only normalizes the gateway-facing interface.
    """

    def __init__(self, descriptor: AssetDescriptor, service: Any):
        self.descriptor = descriptor
        self.service = service

    @property
    def asset_key(self) -> str:
        return self.descriptor.asset_key

    @property
    def asset_id(self) -> str:
        return self.descriptor.asset_id

    @property
    def asset_type(self) -> str:
        return self.descriptor.asset_type

    def start(self) -> None:
        """Optional lifecycle hook. Existing services are started by the gateway application bootstrap."""
        return None

    def stop(self) -> None:
        """Optional lifecycle hook. Existing services are stopped by the gateway application bootstrap."""
        return None

    @abstractmethod
    def get_telemetry(self) -> JsonDict:
        """Return latest asset telemetry using the existing service payload shape."""
        raise NotImplementedError

    @abstractmethod
    def execute_command(self, command_packet: JsonDict) -> JsonDict:
        """Execute one command packet and return the existing response shape."""
        raise NotImplementedError

    def get_state(self) -> Optional[JsonDict]:
        """Return latest state if the underlying service exposes one."""
        return None

    def get_status(self) -> JsonDict:
        """
        Return additive adapter status.

        This status is intentionally separate from the legacy top-level status
        keys in main.py so existing dashboards keep working unchanged.
        """
        status = self.descriptor.to_status()
        status.update(
            {
                "adapter_class": self.__class__.__name__,
                "service_class": self.service.__class__.__name__ if self.service is not None else None,
            }
        )
        try:
            status["state"] = self.get_state()
        except Exception as error:
            status["state_error"] = str(error)
        return status

    def _response(
        self,
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
