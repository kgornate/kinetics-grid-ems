from fastapi import APIRouter, Request
router=APIRouter()
@router.get('/api/registers/map')
def register_map(request: Request)->dict:
    d=request.app.state.container.register_map.to_dict()
    d['runtime_source_count']=len(request.app.state.container.sources)
    d['runtime_total_point_count']=d['point_count']*len(request.app.state.container.sources)
    return d
@router.get('/api/registers/raw')
def raw_registers(request: Request, asset_id: str|None=None, category: str|None=None, key_only: bool=False, source_id: str|None=None)->dict:
    assets=request.app.state.container.asset_manager.snapshot(asset_id=asset_id,category=category,key_only=key_only,source_id=source_id); items=[]
    for aid,a in assets.items():
        for s in a.get('signals',{}).values(): items.append({'source_id':a.get('source_id'),'asset_id':aid,'signal_name':s['name'],'display_name':s['display_name'],'address':s['address'],'raw_registers':s.get('raw_registers',[]),'value':s.get('value'),'quality':s.get('quality'),'category':s.get('category')})
    return {'items':items,'count':len(items),'source_id':source_id}
