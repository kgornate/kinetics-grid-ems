from fastapi import APIRouter, Request, HTTPException
router=APIRouter()
@router.get('/api/assets')
def assets(request: Request, source_id: str|None=None)->dict:
    items=request.app.state.container.asset_manager.asset_list(source_id=source_id)
    return {'items':items,'assets':items,'count':len(items),'source_id':source_id}
@router.get('/api/assets/{asset_id}')
def asset(request: Request, asset_id: str)->dict:
    s=request.app.state.container.asset_manager.snapshot(asset_id=asset_id)
    if asset_id not in s: raise HTTPException(404,'asset not found')
    return s[asset_id]
@router.get('/api/assets/{asset_id}/telemetry')
def asset_telemetry(request: Request, asset_id: str, category: str|None=None, key_only: bool=False, compact: bool=False, page: int=1, page_size: int=0)->dict:
    s=request.app.state.container.asset_manager.snapshot(asset_id=asset_id,category=category,key_only=key_only)
    if asset_id not in s: raise HTTPException(404,'asset not found')
    asset=s[asset_id]
    signals=asset.get('signals',{}) or {}
    total=len(signals)
    if compact:
        signals={k:{kk:vv for kk,vv in v.items() if kk not in ['raw_registers','description']} for k,v in signals.items()}
        asset['signals']=signals
    if page_size and page_size > 0:
        page=max(page,1); page_size=max(1,min(page_size,500))
        items=list(signals.items())
        start=(page-1)*page_size; end=start+page_size
        asset['signals']={k:v for k,v in items[start:end]}
        asset['pagination']={'page':page,'page_size':page_size,'total':total,'returned':len(asset['signals']),'has_more':end<total}
    return asset
