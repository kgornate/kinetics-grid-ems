from fastapi import APIRouter, Request, HTTPException, Response
router=APIRouter()
@router.get('/api/logs')
def logs(request: Request,severity: str|None=None,event_type: str|None=None,source: str|None=None,asset_id: str|None=None,from_time: str|None=None,to_time: str|None=None,search: str|None=None,limit: int|None=None,offset: int=0,order: str='desc')->dict:
    c=request.app.state.container
    if not c.storage: raise HTTPException(503,'storage disabled')
    return c.storage.query_events(severity=severity,event_type=event_type,source=source,asset_id=asset_id,from_time=from_time,to_time=to_time,search=search,limit=min(limit or c.config.logging.default_query_limit,c.config.logging.max_query_limit),offset=max(offset,0),order=order)
@router.get('/api/logs/summary')
def summary(request: Request, from_time: str|None=None, to_time: str|None=None)->dict:
    c=request.app.state.container
    if not c.storage: raise HTTPException(503,'storage disabled')
    return c.storage.event_summary(from_time=from_time,to_time=to_time)
@router.get('/api/logs/filters')
def filters(request: Request)->dict:
    c=request.app.state.container
    if not c.storage: raise HTTPException(503,'storage disabled')
    return c.storage.log_filter_options()
@router.get('/api/logs/export.csv')
def export_csv(request: Request,severity: str|None=None,event_type: str|None=None,source: str|None=None,asset_id: str|None=None,from_time: str|None=None,to_time: str|None=None,search: str|None=None,order: str='desc')->Response:
    c=request.app.state.container
    if not c.storage: raise HTTPException(503,'storage disabled')
    txt=c.storage.export_events_csv(severity=severity,event_type=event_type,source=source,asset_id=asset_id,from_time=from_time,to_time=to_time,search=search,limit=c.config.logging.export_max_rows,offset=0,order=order)
    return Response(content=txt,media_type='text/csv',headers={'Content-Disposition':'attachment; filename=northbound_ems_gateway_logs.csv'})
@router.post('/api/logs/test')
def test_log(request: Request,severity: str='info',event_type: str='manual_test_log',message: str='Manual test log from API',asset_id: str|None=None)->dict:
    c=request.app.state.container; log_id=c.event_logger.log(severity,event_type,message,{'created_by':'/api/logs/test'},source='api',asset_id=asset_id)
    return {'inserted':log_id is not None,'id':log_id}
