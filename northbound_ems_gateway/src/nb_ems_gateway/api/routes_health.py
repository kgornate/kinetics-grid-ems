from fastapi import APIRouter, Request
router=APIRouter()
@router.get('/api/health')
def health(request: Request)->dict:
    c=request.app.state.container; d=c.health_engine.snapshot(); d['storage']=c.storage_status(); d['server_upload']=c.server_upload_status(); d['logging']={'enabled':c.config.logging.enabled,'min_severity':c.config.logging.min_severity,'events_count':d['storage'].get('tables',{}).get('gateway_events') if d.get('storage') else None}; return d
