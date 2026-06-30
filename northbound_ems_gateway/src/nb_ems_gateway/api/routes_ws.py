import asyncio
from fastapi import APIRouter, WebSocket
router=APIRouter()
@router.websocket('/ws/telemetry')
async def ws(websocket: WebSocket):
    await websocket.accept(); c=websocket.app.state.container
    try:
        while True:
            await websocket.send_json({'assets':c.asset_manager.snapshot(key_only=True)}); await asyncio.sleep(2)
    except Exception: return
