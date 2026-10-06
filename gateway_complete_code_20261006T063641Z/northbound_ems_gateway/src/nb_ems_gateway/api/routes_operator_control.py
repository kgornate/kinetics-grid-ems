from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from nb_ems_gateway.auth.security import CurrentUser, audit_auth_event, require_roles
from nb_ems_gateway.operator_control.settings import (
    ControllerSettingsStore,
    ControllerSettingsValidationError,
)
from nb_ems_gateway.operator_control.store import ControllerMonitorStore

router = APIRouter()


def _store() -> ControllerMonitorStore:
    # Paths can be overridden for lab/test deployments through environment vars.
    return ControllerMonitorStore()


def _settings_store() -> ControllerSettingsStore:
    return ControllerSettingsStore()


class ControllerSettingsPatch(BaseModel):
    derate_soc_limit: float | None = Field(default=None, ge=0, le=100)
    derate_power_kw: float | None = Field(default=None, gt=0, le=100)
    high_limit: float | None = Field(default=None, ge=0, le=100)
    recovery_limit: float | None = Field(default=None, ge=0, le=100)
    low_cutoff_limit: float | None = Field(default=None, ge=0, le=100)
    low_recovery_limit: float | None = Field(default=None, ge=0, le=100)


@router.get('/api/controller/status')
def controller_status() -> dict:
    """Current normalized SOC/Solis automatic-controller status for operator UI."""
    return _store().read_status()


@router.get('/api/controller/history')
def controller_history(
    event_type: str | None = None,
    severity: str | None = None,
    device: str | None = None,
    result: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    order: str = Query(default='desc', pattern='^(asc|desc)$'),
) -> dict:
    """Meaningful controller transitions, commands, errors, and comm events."""
    return _store().query_events(
        event_type=event_type,
        severity=severity,
        device=device,
        result=result,
        from_time=from_time,
        to_time=to_time,
        limit=limit,
        offset=offset,
        order=order,
    )


@router.get('/api/controller/settings')
def controller_settings() -> dict:
    """Read-only threshold view for operator/customer UI.

    Normal authenticated users may read the active thresholds. Only internal_admin
    can change them through /api/admin/controller/settings.
    """
    settings = _settings_store().ensure()
    status = _store().read_status()
    thresholds = status.get('thresholds') or {}
    return {
        **settings,
        'low_cutoff_enabled': bool(thresholds.get('low_cutoff_enabled', False)),
        'write_role': 'internal_admin',
        'runtime_reload': 'next_controller_cycle',
    }


@router.patch('/api/admin/controller/settings')
async def update_controller_settings(
    request: Request,
    body: ControllerSettingsPatch,
    user: CurrentUser = Depends(require_roles('internal_admin')),
) -> dict:
    """Update SOC thresholds and solar derating target. Internal-admin only."""
    patch = body.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(status_code=400, detail='At least one threshold value is required')

    store = _settings_store()
    try:
        result = store.update(patch, updated_by=user.username)
    except ControllerSettingsValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_auth_event(
        request,
        'controller_settings_update',
        'SOC controller thresholds/derating settings updated',
        {
            'changes': result.get('changes') or {},
            'revision': result.get('revision'),
            'settings_path': result.get('settings_path'),
        },
        user=user,
    )

    if result.get('changed'):
        current_status = _store().read_status()
        ctrl = current_status.get('controller') or {}
        bess = current_status.get('bess') or {}
        solis = current_status.get('solis') or {}
        try:
            _store().append_event(
                event_type='controller_settings_changed',
                device='Controller',
                result='success',
                message='SOC control thresholds/derating settings changed by internal administrator',
                controller_state=ctrl.get('state'),
                decision=ctrl.get('decision'),
                soc_x=(bess.get('X') or {}).get('soc_percent'),
                soc_y=(bess.get('Y') or {}).get('soc_percent'),
                solis_state=solis.get('state'),
                solis_power_w=solis.get('active_power_w'),
                payload={
                    'changed_by': user.username,
                    'role': user.role,
                    'revision': result.get('revision'),
                    'changes': result.get('changes') or {},
                    'new_settings': result.get('settings') or {},
                },
            )
        except Exception:
            # The settings write itself must not be rolled back only because the
            # secondary operator-history audit DB is temporarily unavailable.
            pass

    return {
        'ok': True,
        **result,
        'changed_by': user.username,
        'effective': 'next_controller_cycle',
    }


@router.get('/api/solis/status')
def solis_status() -> dict:
    """Small Solis-specific view derived from the controller status snapshot."""
    status = _store().read_status()
    if not status.get('available'):
        return {
            'available': False,
            'reason': status.get('reason'),
            'error': status.get('error'),
            'solis': None,
        }
    return {
        'available': True,
        'timestamp_utc': status.get('timestamp_utc'),
        'controller_state': (status.get('controller') or {}).get('state'),
        'decision': (status.get('controller') or {}).get('decision'),
        'thresholds': status.get('thresholds') or {},
        'solis': status.get('solis') or {},
    }


@router.get('/api/solis/history')
def solis_history(
    event_type: str | None = None,
    result: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    order: str = Query(default='desc', pattern='^(asc|desc)$'),
) -> dict:
    """Solis command/state/communication history for the operator UI."""
    return _store().query_events(
        event_type=event_type,
        device='Solis',
        result=result,
        from_time=from_time,
        to_time=to_time,
        limit=limit,
        offset=offset,
        order=order,
    )
