from fastapi import APIRouter, Request
router=APIRouter()
@router.get('/api/health')
def health(request: Request)->dict:
    c=request.app.state.container
    d=c.health_engine.snapshot()
    try:
        storage_status=c.storage_status()
    except Exception as exc:
        storage_status={'enabled':c.config.storage.enabled,'status_error':str(exc),'tables':{}}
    d['storage']=storage_status
    d['server_upload']=c.server_upload_status()
    d['logging']={
        'enabled':c.config.logging.enabled,
        'min_severity':c.config.logging.min_severity,
        'events_count':storage_status.get('tables',{}).get('gateway_events') if isinstance(storage_status,dict) else None,
    }
    return d
