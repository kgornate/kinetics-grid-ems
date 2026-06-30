from fastapi import APIRouter, Request, HTTPException
router=APIRouter()
@router.get('/api/assets')
def assets(request: Request)->dict: return {'items':request.app.state.container.asset_manager.asset_list()}
@router.get('/api/assets/{asset_id}')
def asset(request: Request, asset_id: str)->dict:
    s=request.app.state.container.asset_manager.snapshot(asset_id=asset_id)
    if asset_id not in s: raise HTTPException(404,'asset not found')
    return s[asset_id]
@router.get('/api/assets/{asset_id}/telemetry')
def asset_telemetry(request: Request, asset_id: str, category: str|None=None, key_only: bool=False)->dict:
    s=request.app.state.container.asset_manager.snapshot(asset_id=asset_id,category=category,key_only=key_only)
    if asset_id not in s: raise HTTPException(404,'asset not found')
    return s[asset_id]
