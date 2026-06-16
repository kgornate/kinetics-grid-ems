"""Storage manager abstraction for telemetry, event, and error logs.

StorageManager is the service-facing logging interface. It currently uses the
existing CSV StorageLogger backend, while hiding that implementation behind
small telemetry/event/error store facades. This keeps current CSV files and Log
HTTP APIs compatible while making a future SQLite/cloud backend easier to add.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from services.storage_logger import StorageLogger
from .telemetry_store import TelemetryStore
from .event_store import EventStore
from .error_store import ErrorStore
from .storage_status import StorageStatus


class StorageManager:
    """Compatibility facade over the active storage backend."""

    backend_name = "csv_storage_logger"

    def __init__(
        self,
        base_path: str,
        gateway_id: str = "imx93_gateway_1",
        asset_id: str = "chiller_1",
        asset_type: Optional[str] = None,
        backend: Optional[Any] = None,
    ):
        self.backend = backend or StorageLogger(
            base_path=base_path,
            gateway_id=gateway_id,
            asset_id=asset_id,
            asset_type=asset_type,
        )
        # Backward-compatible alias used by existing code and tests.
        self.logger = self.backend
        self.telemetry = TelemetryStore(self.backend)
        self.events = EventStore(self.backend)
        self.errors = ErrorStore(self.backend)
        self.status = StorageStatus(self.backend)

    def initialize(self) -> bool:
        return bool(self.backend.initialize())

    def log_telemetry(self, *args: Any, **kwargs: Any) -> bool:
        return self.telemetry.log(*args, **kwargs)

    def write_telemetry(self, *args: Any, **kwargs: Any) -> bool:
        return self.log_telemetry(*args, **kwargs)

    def append_telemetry(self, *args: Any, **kwargs: Any) -> bool:
        return self.log_telemetry(*args, **kwargs)

    def log_asset_telemetry(self, asset_id: str, telemetry: Dict[str, Any], **kwargs: Any) -> bool:
        return self.log_telemetry(asset_id, telemetry)

    def log_event(self, *args: Any, **kwargs: Any) -> bool:
        return self.events.log(*args, **kwargs)

    def write_event(self, *args: Any, **kwargs: Any) -> bool:
        return self.log_event(*args, **kwargs)

    def append_event(self, *args: Any, **kwargs: Any) -> bool:
        return self.log_event(*args, **kwargs)

    def log_asset_event(self, asset_id: str, event: Dict[str, Any], **kwargs: Any) -> bool:
        return self.log_event(asset_id, event)

    def log_error(self, *args: Any, **kwargs: Any) -> bool:
        return self.errors.log(*args, **kwargs)

    def write_error(self, *args: Any, **kwargs: Any) -> bool:
        return self.log_error(*args, **kwargs)

    def append_error(self, *args: Any, **kwargs: Any) -> bool:
        return self.log_error(*args, **kwargs)

    def get_status(self) -> Dict[str, Any]:
        status = self.status.get_status()
        status.update(
            {
                "storage_manager": self.__class__.__name__,
                "backend": self.backend_name,
                "stores": {
                    "telemetry": self.telemetry.get_status(),
                    "events": self.events.get_status(),
                    "errors": self.errors.get_status(),
                },
            }
        )
        return status

    def get_health(self) -> Dict[str, Any]:
        health = self.status.get_health()
        health.update(
            {
                "storage_manager": self.__class__.__name__,
                "backend": self.backend_name,
                "stores": {
                    "telemetry": self.telemetry.get_status(),
                    "events": self.events.get_status(),
                    "errors": self.errors.get_status(),
                },
            }
        )
        return health

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attributes to the backend for compatibility."""
        return getattr(self.backend, name)
