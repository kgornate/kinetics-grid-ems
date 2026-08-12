from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from nb_ems_gateway.auth.security import CurrentUser, audit_auth_event, require_roles

router = APIRouter()

_ALLOWED_UPDATE_FIELDS: dict[str, set[str]] = {
    'polling': {'default_interval_sec', 'fast_interval_sec', 'slow_interval_sec', 'max_registers_per_read'},
    'logging': {'min_severity', 'store_access_logs', 'store_poll_events', 'store_server_upload_events', 'store_telemetry_quality_events', 'max_query_limit', 'default_query_limit', 'retention_days', 'export_max_rows'},
    'storage': {'min_free_space_mb', 'max_db_size_mb', 'retention_days', 'store_mode', 'snapshot_interval_sec', 'vacuum_after_cleanup'},
    'server_upload': {'enabled', 'endpoint_url', 'network_interface', 'upload_interval_sec', 'timeout_sec', 'payload_mode', 'buffer_when_offline', 'max_queue_size', 'verify_tls'},
}

_SECRET_FIELDS = {'api_key', 'jwt_secret', 'password_hash'}


class ConfigUpdateRequest(BaseModel):
    section: str = Field(..., description='Config section, for example storage, logging, polling, server_upload')
    values: dict[str, Any]


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ('***redacted***' if any(s in k.lower() for s in _SECRET_FIELDS) else _redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _config_snapshot(config) -> dict[str, Any]:
    return _redact(config.model_dump())


@router.get('/api/config/runtime')
async def get_runtime_config(request: Request, user: CurrentUser = Depends(require_roles('customer_admin', 'internal_admin'))) -> dict[str, Any]:
    return {'config': _config_snapshot(request.app.state.container.config), 'user': user.model_dump()}


@router.post('/api/config/runtime')
async def update_runtime_config(request: Request, body: ConfigUpdateRequest, user: CurrentUser = Depends(require_roles('customer_admin', 'internal_admin'))) -> dict[str, Any]:
    section = body.section.strip()
    if section not in _ALLOWED_UPDATE_FIELDS:
        raise HTTPException(400, f'Config section not allowed: {section}')
    section_obj = getattr(request.app.state.container.config, section, None)
    if section_obj is None:
        raise HTTPException(400, f'Config section not found: {section}')

    allowed = _ALLOWED_UPDATE_FIELDS[section]
    applied: dict[str, dict[str, Any]] = {}
    ignored: dict[str, Any] = {}

    for key, value in body.values.items():
        if key not in allowed:
            ignored[key] = value
            continue
        if not hasattr(section_obj, key):
            ignored[key] = value
            continue
        old = getattr(section_obj, key)
        setattr(section_obj, key, value)
        applied[key] = {'old': old, 'new': value}

    # Re-run Pydantic validation on the mutated section by reconstructing it.
    section_cls = section_obj.__class__
    try:
        validated = section_cls(**section_obj.model_dump())
    except Exception as exc:
        # Roll back applied values on validation failure.
        for key, change in applied.items():
            setattr(section_obj, key, change['old'])
        raise HTTPException(400, f'Invalid config update: {exc}') from exc
    setattr(request.app.state.container.config, section, validated)

    audit_auth_event(
        request,
        'config_runtime_update',
        f'Runtime config updated: {section}',
        {'section': section, 'applied': _redact(applied), 'ignored': _redact(ignored)},
        user=user,
    )
    return {'ok': True, 'section': section, 'applied': _redact(applied), 'ignored': _redact(ignored)}
