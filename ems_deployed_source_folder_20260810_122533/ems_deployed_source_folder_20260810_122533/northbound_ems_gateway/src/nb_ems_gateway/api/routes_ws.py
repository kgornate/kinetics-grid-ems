import asyncio

from fastapi import APIRouter, WebSocket, WebSocketException, status

from nb_ems_gateway.auth.security import verify_access_token

router = APIRouter()


@router.websocket('/ws/telemetry')
async def ws(websocket: WebSocket):
    c = websocket.app.state.container
    token = websocket.query_params.get('token') or websocket.query_params.get('access_token')
    if c.config.auth.enabled:
        if not token:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason='Missing auth token')
        verify_access_token(c.config.auth, token)
    await websocket.accept()
    try:
        while True:
            await websocket.send_json({'assets': c.asset_manager.snapshot(key_only=True)})
            await asyncio.sleep(2)
    except Exception:
        return
