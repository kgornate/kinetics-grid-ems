from fastapi import APIRouter, Request
router=APIRouter()
@router.get('/api/telemetry')
def telemetry(request: Request, category: str|None=None, key_only: bool=False, source_id: str|None=None)->dict:
    return {'assets':request.app.state.container.asset_manager.snapshot(category=category,key_only=key_only,source_id=source_id),'source_id':source_id}
@router.get('/api/telemetry/key-signals')
def key_signals(request: Request, source_id: str|None=None)->dict:
    return {'assets':request.app.state.container.asset_manager.snapshot(key_only=True,source_id=source_id),'source_id':source_id}
@router.get('/api/alarms')
def alarms(request: Request, source_id: str|None=None)->dict:
    return request.app.state.container.alarm_engine.snapshot(source_id=source_id)
