from __future__ import annotations
from fastapi import FastAPI, Request
from .routes_health import router as health_router
from .routes_assets import router as assets_router
from .routes_telemetry import router as telemetry_router
from .routes_storage import router as storage_router
from .routes_registers import router as registers_router
from .routes_server_upload import router as server_upload_router
from .routes_logs import router as logs_router
from .routes_ws import router as ws_router

def create_app(container) -> FastAPI:
    app=FastAPI(title='NorthBound EMS Gateway',version='0.5.0'); app.state.container=container
    @app.middleware('http')
    async def access_log(request: Request, call_next):
        response=await call_next(request)
        if container.config.logging.store_access_logs and request.url.path not in ['/api/health']:
            container.event_logger.debug('api_access',f'{request.method} {request.url.path} -> {response.status_code}',{'method':request.method,'path':request.url.path,'status_code':response.status_code,'client':request.client.host if request.client else None},source='api')
        return response
    for r in [health_router,assets_router,telemetry_router,storage_router,registers_router,server_upload_router,logs_router,ws_router]: app.include_router(r)
    return app
