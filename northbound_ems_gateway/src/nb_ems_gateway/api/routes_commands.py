from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from nb_ems_gateway.auth.security import CurrentUser, require_roles

router = APIRouter()

class EMSWriteRequest(BaseModel):
    source_id: str
    signal_name: str | None = None
    address: int | None = None
    value: float
    readback: bool = True
    note: str | None = None

class EMSBatchWriteRequest(BaseModel):
    writes: list[EMSWriteRequest] = Field(default_factory=list)
    continue_on_error: bool = False
    note: str | None = None

def _require_commands_enabled(c: Any) -> None:
    if not c.config.api.commands_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Command APIs are disabled by config.api.commands_enabled')

def _point_for_request(c: Any, body: EMSWriteRequest):
    if body.signal_name:
        p = c.register_map.find_point(signal_name=body.signal_name)
    elif body.address is not None:
        p = c.register_map.find_point(address=body.address)
    else:
        raise HTTPException(400, 'Either signal_name or address is required')
    if not p:
        raise HTTPException(404, 'register point not found')
    if int(p.rw or 0) != 1:
        raise HTTPException(403, f'Register {p.signal_name} at address {p.address} is read-only')
    return p

@router.get('/api/commands/ems/registers')
async def ems_command_registers(request: Request, source_id: str | None=None, user: CurrentUser = Depends(require_roles('internal_admin'))) -> dict:
    c = request.app.state.container
    _require_commands_enabled(c)
    if source_id and not c.source_by_id(source_id):
        raise HTTPException(404, 'source not found')
    sources = [source_id] if source_id else [s.source_id for s in c.sources]
    items=[]
    for sid in sources:
        source = c.source_by_id(sid)
        for p in c.register_map.writable_points:
            items.append({
                'source_id': sid,
                'source_display_name': source.display_name if source else sid,
                'signal_name': p.signal_name,
                'display_name': p.point_name,
                'asset_id': f'{sid}_ems_system',
                'base_asset_id': p.asset_id,
                'address': p.address,
                'register_qty': p.register_qty,
                'point_type': p.point_type,
                'unit': p.unit,
                'description': p.description,
                'category': p.category,
                'rw': p.rw,
            })
    return {'items': items, 'count': len(items), 'source_id': source_id, 'user': user.model_dump()}

@router.post('/api/commands/ems/write')
async def ems_write(request: Request, body: EMSWriteRequest, user: CurrentUser = Depends(require_roles('internal_admin'))) -> dict:
    c = request.app.state.container
    _require_commands_enabled(c)
    if not c.control_service:
        raise HTTPException(503, 'control service not initialized')
    p = _point_for_request(c, body)
    try:
        result = c.control_service.write_value(body.source_id, p.signal_name, body.value, readback=body.readback)
        result['ok'] = True
        result['note'] = body.note
        result['user'] = user.username
        return result
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc

@router.post('/api/commands/ems/batch')
async def ems_batch_write(request: Request, body: EMSBatchWriteRequest, user: CurrentUser = Depends(require_roles('internal_admin'))) -> dict:
    c = request.app.state.container
    _require_commands_enabled(c)
    results=[]
    ok=True
    for item in body.writes:
        try:
            p = _point_for_request(c, item)
            res = c.control_service.write_value(item.source_id, p.signal_name, item.value, readback=item.readback)
            res['ok'] = True
            results.append(res)
        except Exception as exc:
            ok=False
            results.append({'ok': False, 'source_id': item.source_id, 'signal_name': item.signal_name, 'address': item.address, 'error': str(exc)})
            if not body.continue_on_error:
                break
    return {'ok': ok, 'results': results, 'count': len(results), 'note': body.note, 'user': user.username}
