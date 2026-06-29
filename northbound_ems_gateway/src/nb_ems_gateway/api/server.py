from __future__ import annotations

from fastapi import FastAPI

from nb_ems_gateway.app.dependency_container import DependencyContainer
from .routes_alarms import router as alarms_router
from .routes_assets import router as assets_router
from .routes_health import router as health_router
from .routes_registers import router as registers_router
from .routes_telemetry import router as telemetry_router
from .routes_storage import router as storage_router
from .routes_server_upload import router as server_upload_router
from .routes_ws import router as ws_router


def create_app(container: DependencyContainer) -> FastAPI:
    app = FastAPI(
        title="NorthBound EMS Gateway API",
        description="Read-only API for Chinese EMS north-bound Modbus TCP integration.",
        version="0.3.0",
    )
    app.state.container = container
    app.include_router(health_router)
    app.include_router(assets_router)
    app.include_router(telemetry_router)
    app.include_router(alarms_router)
    app.include_router(registers_router)
    app.include_router(storage_router)
    app.include_router(server_upload_router)
    app.include_router(ws_router)
    return app
