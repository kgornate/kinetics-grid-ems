from fastapi import APIRouter, Request, HTTPException
router=APIRouter()
@router.get('/api/storage/status')
def status(request: Request)->dict: return request.app.state.container.storage_status()
@router.get('/api/storage/health')
def storage_health(request: Request)->dict:
    store=request.app.state.container.storage
    if not store: return {'enabled':False}
    return store.health()
@router.post('/api/storage/cleanup')
def cleanup(request: Request, retention_days: int|None=None, vacuum: bool|None=None)->dict:
    store=request.app.state.container.storage
    if not store: raise HTTPException(503,'storage disabled')
    return store.cleanup(retention_days=retention_days, vacuum=vacuum)
@router.post('/api/storage/vacuum')
def vacuum(request: Request)->dict:
    store=request.app.state.container.storage
    if not store: raise HTTPException(503,'storage disabled')
    return store.vacuum()
@router.get('/api/storage/snapshots')
def snapshots(request: Request, asset_id: str|None=None, limit: int=10)->dict:
    store=request.app.state.container.storage
    if not store: raise HTTPException(503,'storage disabled')
    return {'items':store.query_snapshots(asset_id=asset_id,limit=min(limit,500))}
@router.get('/api/storage/points')
def points(request: Request, asset_id: str, signal_name: str, limit: int=100)->dict:
    store=request.app.state.container.storage
    if not store: raise HTTPException(503,'storage disabled')
    return {'items':store.query_points(asset_id=asset_id,signal_name=signal_name,limit=min(limit,1000))}
