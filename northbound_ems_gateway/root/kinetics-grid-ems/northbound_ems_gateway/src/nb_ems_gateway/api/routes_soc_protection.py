from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from nb_ems_gateway.auth.security import CurrentUser, require_roles

router = APIRouter()


class SOCProtectionRuntimeRequest(BaseModel):
    enabled: bool | None = None
    dry_run: bool | None = None
    note: str | None = None


class SOCProtectionSolarRequest(BaseModel):
    available: bool | None = None
    generation_kw: float | None = None
    note: str | None = None


def _controller(request: Request):
    c = request.app.state.container
    ctrl = getattr(c, 'soc_protection_controller', None)
    if not ctrl:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='SOC protection controller is not initialized')
    return ctrl


@router.get('/api/control/soc-protection/status')
async def soc_protection_status(request: Request, user: CurrentUser = Depends(require_roles('customer_admin', 'internal_admin'))) -> dict:
    return _controller(request).status.to_dict()


@router.post('/api/control/soc-protection/runtime')
async def soc_protection_runtime(body: SOCProtectionRuntimeRequest, request: Request, user: CurrentUser = Depends(require_roles('internal_admin'))) -> dict:
    return _controller(request).set_runtime(enabled=body.enabled, dry_run=body.dry_run, note=body.note, user=user.username)


@router.post('/api/control/soc-protection/solar')
async def soc_protection_solar(body: SOCProtectionSolarRequest, request: Request, user: CurrentUser = Depends(require_roles('internal_admin'))) -> dict:
    return _controller(request).set_solar_status(available=body.available, generation_kw=body.generation_kw, note=body.note, user=user.username)


@router.post('/api/control/soc-protection/evaluate-once')
async def soc_protection_evaluate_once(request: Request, force: bool = False, user: CurrentUser = Depends(require_roles('internal_admin'))) -> dict:
    try:
        result = await _controller(request).evaluate_once(trigger=f'api:{user.username}', force=force)
        result['user'] = user.username
        return result
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
