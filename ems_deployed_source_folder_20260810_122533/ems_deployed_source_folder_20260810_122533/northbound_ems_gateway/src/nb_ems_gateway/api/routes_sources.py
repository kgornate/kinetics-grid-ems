from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException

router = APIRouter()

@router.get('/api/sources')
def sources(request: Request) -> dict:
    c = request.app.state.container
    items = []
    for s in c.sources:
        summary = c.asset_manager.source_summary(s.source_id)
        items.append({
            'source_id': s.source_id,
            'display_name': s.display_name,
            'host': s.host,
            'port': s.port,
            'unit_id': s.unit_id,
            'interface': s.interface,
            'protocol': s.protocol,
            'enabled': s.enabled,
            **summary,
        })
    return {'items': items, 'count': len(items)}

@router.get('/api/sources/summary')
def source_summary(request: Request) -> dict:
    c = request.app.state.container
    return {'items': [{**c.asset_manager.source_summary(s.source_id), 'display_name': s.display_name, 'host': s.host, 'port': s.port} for s in c.sources]}

@router.get('/api/sources/{source_id}')
def source_detail(request: Request, source_id: str) -> dict:
    c = request.app.state.container
    s = c.source_by_id(source_id)
    if not s:
        raise HTTPException(404, 'source not found')
    return {**s.model_dump(), **c.asset_manager.source_summary(source_id)}

@router.get('/api/sources/{source_id}/assets')
def source_assets(request: Request, source_id: str) -> dict:
    c = request.app.state.container
    if not c.source_by_id(source_id):
        raise HTTPException(404, 'source not found')
    items = c.asset_manager.asset_list(source_id=source_id)
    return {'source_id': source_id, 'items': items, 'assets': items, 'count': len(items)}

@router.get('/api/sources/{source_id}/telemetry')
def source_telemetry(request: Request, source_id: str, category: str | None=None, key_only: bool=False) -> dict:
    c = request.app.state.container
    if not c.source_by_id(source_id):
        raise HTTPException(404, 'source not found')
    return {'source_id': source_id, 'assets': c.asset_manager.snapshot(source_id=source_id, category=category, key_only=key_only)}
