from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/telemetry")
async def telemetry_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            container = websocket.app.state.container
            await websocket.send_json(
                {
                    "gateway_id": container.config.gateway.id,
                    "mode": container.config.gateway.mode,
                    "assets": container.asset_manager.telemetry_snapshot(),
                }
            )
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
