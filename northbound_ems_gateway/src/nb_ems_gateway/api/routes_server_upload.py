from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/api/server-upload/status")
def get_server_upload_status(request: Request) -> dict:
    container = request.app.state.container
    return container.server_upload_status()


@router.post("/api/server-upload/upload-once")
async def upload_once(request: Request) -> dict:
    """Diagnostic upload trigger.

    This does not write to the Chinese EMS and does not execute any control
    command. It only pushes the latest read-only snapshot to the configured HTTPS
    REST backend when server_upload.enabled is true.
    """
    container = request.app.state.container
    if not container.server_upload_service:
        raise HTTPException(status_code=503, detail="Server upload service is not configured")
    return await container.server_upload_service.upload_once()
