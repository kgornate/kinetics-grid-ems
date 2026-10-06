from fastapi import APIRouter, Request
router=APIRouter()
@router.get('/api/health')
def health(request: Request)->dict:
    c=request.app.state.container
    d=c.health_engine.snapshot()
    try:
        # Lightweight health path.
        #
        # Do NOT call c.storage_status() here because SQLiteStore.status()
        # performs COUNT(*) across the telemetry/event tables. On a large
        # field database this can make the health endpoint block for many
        # seconds. S3 polls this route frequently, so /api/health must remain
        # constant-time and lightweight.
        storage_status = (
            c.storage.health()
            if c.storage
            else {'enabled': False}
        )
    except Exception as exc:
        storage_status={
            'enabled':c.config.storage.enabled,
            'status_error':str(exc),
        }
    d['storage']=storage_status
    d['server_upload']=c.server_upload_status()
    d['fast_bess_logger']=c.fast_bess_logger_status()
    d['general_asset_live_publisher']=c.general_asset_live_publisher_status()
    if getattr(c, 'soc_protection_controller', None):
        d['soc_protection']=c.soc_protection_controller.status.to_dict()
    d['logging']={
        'enabled':c.config.logging.enabled,
        'min_severity':c.config.logging.min_severity,
        'events_count':storage_status.get('tables',{}).get('gateway_events') if isinstance(storage_status,dict) else None,
    }
    return d
