from fastapi import APIRouter, Request
router=APIRouter()
@router.get('/api/registers/map')
def register_map(request: Request)->dict: return request.app.state.container.register_map.to_dict()
@router.get('/api/registers/raw')
def raw_registers(request: Request, asset_id: str|None=None, category: str|None=None, key_only: bool=False)->dict:
    assets=request.app.state.container.asset_manager.snapshot(asset_id=asset_id,category=category,key_only=key_only); items=[]
    for aid,a in assets.items():
        for s in a.get('signals',{}).values(): items.append({'asset_id':aid,'signal_name':s['name'],'display_name':s['display_name'],'address':s['address'],'raw_registers':s.get('raw_registers',[]),'value':s.get('value'),'quality':s.get('quality'),'category':s.get('category')})
    return {'items':items,'count':len(items)}
