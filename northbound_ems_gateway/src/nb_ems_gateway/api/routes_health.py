from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/health")
def get_health(request: Request) -> dict:
    container = request.app.state.container
    data = container.health_engine.snapshot()
    data["poll_errors"] = container.latest_poll_errors
    data["commands_enabled"] = container.config.api.commands_enabled
    data["storage"] = container.storage_status()
    data["server_upload"] = container.server_upload_status()
    return data
