from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/alarms")
def get_alarms(request: Request) -> dict:
    container = request.app.state.container
    return container.alarm_engine.snapshot()
