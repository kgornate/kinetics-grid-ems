"""Storage status helpers."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict


class StorageStatus:
    """Build status/health summaries for the active storage backend."""

    def __init__(self, backend: Any):
        self.backend = backend

    def get_status(self) -> Dict[str, Any]:
        try:
            status = dict(self.backend.get_status())
        except Exception as error:
            return {
                "status": "error",
                "logger_status": "status_read_failed",
                "error": str(error),
            }

        status.setdefault("status", "ok" if status.get("logger_status") == "ok" else "warning")
        return status

    def get_health(self) -> Dict[str, Any]:
        status = self.get_status()
        base_path = Path(str(status.get("base_path", ""))) if status.get("base_path") else None
        disk = {
            "disk_total_bytes": 0,
            "disk_used_bytes": 0,
            "disk_free_bytes": 0,
            "disk_used_percent": None,
        }
        if base_path is not None:
            try:
                usage = shutil.disk_usage(str(base_path if base_path.exists() else base_path.parent or "/"))
                disk["disk_total_bytes"] = usage.total
                disk["disk_used_bytes"] = usage.used
                disk["disk_free_bytes"] = usage.free
                disk["disk_used_percent"] = round((usage.used / usage.total) * 100, 2) if usage.total else None
            except Exception as error:
                disk["disk_error"] = str(error)

        logger_status = str(status.get("logger_status", "unknown"))
        healthy = logger_status == "ok"
        return {
            "status": "healthy" if healthy else "degraded",
            "logger_status": logger_status,
            "asset_id": status.get("asset_id"),
            "asset_type": status.get("asset_type"),
            "base_path": status.get("base_path"),
            "telemetry_file": status.get("telemetry_file"),
            "event_file": status.get("event_file"),
            "error_file": status.get("error_file"),
            **disk,
        }
