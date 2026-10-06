from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from nb_ems_gateway.auth.security import CurrentUser, require_roles
from nb_ems_gateway.control.models import GridModeRequest, PowerCommandRequest, SiteGridModeRequest, SitePowerCommandRequest, SiteStandbyRequest, StandbyRequest

router = APIRouter()

def _service(request: Request):
    c = request.app.state.container
    if not c.config.control.enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Control APIs are disabled by config.control.enabled')
    if not c.config.api.commands_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Command/control APIs are disabled by config.api.commands_enabled')
    if not c.control_service:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Control service is not initialized')
    return c.control_service

@router.post('/api/control/sources/{source_id}/grid-mode')
async def source_grid_mode(source_id: str, body: GridModeRequest, request: Request, user: CurrentUser = Depends(require_roles('internal_admin'))) -> dict:
    try:
        res = await _service(request).switch_grid_mode(source_id, body.target_mode, readback=body.readback, timeout_sec=body.timeout_sec, wait_for_voltage_stable=body.wait_for_voltage_stable, note=body.note)
        res['user'] = user.username
        return res
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc

@router.post('/api/control/site/grid-mode')
async def site_grid_mode(body: SiteGridModeRequest, request: Request, user: CurrentUser = Depends(require_roles('internal_admin'))) -> dict:
    try:
        res = await _service(request).switch_site_grid_mode(target_mode=body.target_mode, source_ids=body.source_ids, source_order=body.source_order, readback=body.readback, timeout_sec=body.timeout_sec, wait_for_voltage_stable=body.wait_for_voltage_stable, inter_source_delay_sec=body.inter_source_delay_sec, note=body.note)
        res['user'] = user.username
        return res
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc

@router.post('/api/control/sources/{source_id}/charge')
async def source_charge(source_id: str, body: PowerCommandRequest, request: Request, user: CurrentUser = Depends(require_roles('internal_admin'))) -> dict:
    try:
        res = await _service(request).charge(source_id, body.power_kw, readback=body.readback, note=body.note)
        res['user'] = user.username
        return res
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc

@router.post('/api/control/sources/{source_id}/discharge')
async def source_discharge(source_id: str, body: PowerCommandRequest, request: Request, user: CurrentUser = Depends(require_roles('internal_admin'))) -> dict:
    try:
        res = await _service(request).discharge(source_id, body.power_kw, readback=body.readback, note=body.note)
        res['user'] = user.username
        return res
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc

@router.post('/api/control/sources/{source_id}/standby')
async def source_standby(source_id: str, body: StandbyRequest, request: Request, user: CurrentUser = Depends(require_roles('internal_admin'))) -> dict:
    try:
        res = await _service(request).standby(source_id, readback=body.readback, note=body.note)
        res['user'] = user.username
        return res
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc

@router.post('/api/control/site/power')
async def site_power(body: SitePowerCommandRequest, request: Request, user: CurrentUser = Depends(require_roles('internal_admin'))) -> dict:
    try:
        res = await _service(request).site_power(operation=body.operation, total_power_kw=body.total_power_kw, source_ids=body.source_ids, allocation=body.allocation, per_source_power_kw=body.per_source_power_kw, readback=body.readback, note=body.note)
        res['user'] = user.username
        return res
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc

@router.post('/api/control/site/standby')
async def site_standby(body: SiteStandbyRequest, request: Request, user: CurrentUser = Depends(require_roles('internal_admin'))) -> dict:
    try:
        res = await _service(request).site_standby(source_ids=body.source_ids, readback=body.readback, note=body.note)
        res['user'] = user.username
        return res
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
