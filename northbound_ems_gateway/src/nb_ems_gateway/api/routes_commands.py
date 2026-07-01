from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from nb_ems_gateway.auth.security import CurrentUser, audit_auth_event, require_roles
from nb_ems_gateway.decoding.float_codec import decode_float32, encode_float32
from nb_ems_gateway.dictionary.register_map import RegisterPoint

router = APIRouter()

EMS_ASSET_ID = 'ems_system'


class CommandWriteRequest(BaseModel):
    signal_name: str | None = Field(default=None, description='EMS writable signal name, for example remote_mode')
    point_id: str | None = Field(default=None, description='Register map point id, for example p0003')
    address: int | None = Field(default=None, description='Modbus register address')
    value: float = Field(..., description='Engineering value to write. Gateway applies inverse factor before Modbus write.')
    readback: bool = Field(default=True, description='Read the same register after write and return decoded value')
    note: str | None = Field(default=None, max_length=500)


class CommandBatchWriteRequest(BaseModel):
    writes: list[CommandWriteRequest] = Field(..., min_length=1, max_length=50)
    continue_on_error: bool = False


def _ems_writable_points(request: Request) -> list[RegisterPoint]:
    return [p for p in request.app.state.container.register_map.points if p.asset_id == EMS_ASSET_ID and int(p.rw or 0) == 1]


def _point_to_command(p: RegisterPoint, latest: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        'id': p.id,
        'asset_id': p.asset_id,
        'asset_display_name': p.asset_display_name,
        'address': p.address,
        'register_qty': p.register_qty,
        'point_name': p.point_name,
        'signal_name': p.signal_name,
        'point_type': p.point_type,
        'unit': p.unit,
        'description': p.description,
        'rw': p.rw,
        'factor': p.factor,
        'category': p.category,
        'latest': latest,
    }


def _find_point(request: Request, body: CommandWriteRequest) -> RegisterPoint:
    points = _ems_writable_points(request)
    signal = (body.signal_name or '').strip()
    point_id = (body.point_id or '').strip()
    for p in points:
        if signal and p.signal_name == signal:
            return p
        if point_id and p.id == point_id:
            return p
        if body.address is not None and p.address == int(body.address):
            return p
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail='EMS writable register not found. Only asset_id=ems_system and rw=1 registers are accepted.',
    )


def _ensure_commands_enabled(request: Request) -> None:
    if not request.app.state.container.config.api.commands_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Command APIs are disabled by gateway config')


def _engineering_to_raw_float(request: Request, point: RegisterPoint, value: float) -> tuple[float, list[int]]:
    factor = float(point.factor or 1.0)
    raw_value = float(value)
    if request.app.state.container.config.decoding.apply_factor:
        if factor == 0:
            raise HTTPException(status_code=400, detail=f'Invalid zero factor for {point.signal_name}')
        raw_value = float(value) / factor
    registers = encode_float32(raw_value, request.app.state.container.config.decoding.byte_order)
    return raw_value, registers


def _decode_engineering_value(request: Request, point: RegisterPoint, registers: list[int]) -> float:
    value = decode_float32(registers, request.app.state.container.config.decoding.byte_order)
    if request.app.state.container.config.decoding.apply_factor:
        value *= float(point.factor or 1.0)
    return value


def _latest_signal(request: Request, point: RegisterPoint) -> dict[str, Any] | None:
    snapshot = request.app.state.container.asset_manager.snapshot(asset_id=point.asset_id)
    asset = snapshot.get(point.asset_id, {})
    signal = (asset.get('signals') or {}).get(point.signal_name)
    return signal if isinstance(signal, dict) else None


def _write_one(request: Request, body: CommandWriteRequest, user: CurrentUser) -> dict[str, Any]:
    _ensure_commands_enabled(request)
    c = request.app.state.container
    reader = getattr(c, 'register_reader', None)
    if reader is None:
        raise HTTPException(status_code=503, detail='Register writer is not available')

    point = _find_point(request, body)
    raw_value, registers = _engineering_to_raw_float(request, point, body.value)

    try:
        reader.write_point(point, registers)
        readback_registers = None
        readback_value = None
        if body.readback:
            readback_registers = reader.read_point(point)
            readback_value = _decode_engineering_value(request, point, readback_registers)
            c.asset_manager.update_signal(point, readback_value, 'good', readback_registers)
        else:
            c.asset_manager.update_signal(point, body.value, 'good', registers)
    except HTTPException:
        raise
    except Exception as exc:
        audit_auth_event(
            request,
            'ems_command_write_failed',
            f'EMS command write failed: {point.signal_name}',
            {'signal_name': point.signal_name, 'address': point.address, 'value': body.value, 'error': str(exc)},
            user=user,
            severity='error',
        )
        raise HTTPException(status_code=502, detail=f'Modbus write failed for {point.signal_name}: {exc}') from exc

    result = {
        'ok': True,
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'asset_id': point.asset_id,
        'point_id': point.id,
        'signal_name': point.signal_name,
        'point_name': point.point_name,
        'address': point.address,
        'register_qty': point.register_qty,
        'requested_value': body.value,
        'raw_float_written': raw_value,
        'raw_registers_written': registers,
        'readback_enabled': body.readback,
        'readback_value': readback_value,
        'readback_registers': readback_registers,
        'unit': point.unit,
        'description': point.description,
        'user': user.model_dump(),
    }
    audit_auth_event(
        request,
        'ems_command_write_success',
        f'EMS command write success: {point.signal_name}={body.value}',
        {k: v for k, v in result.items() if k != 'user'},
        user=user,
        severity='warning',
    )
    return result


@router.get('/api/commands/ems/registers')
async def ems_command_registers(request: Request, user: CurrentUser = Depends(require_roles('internal_admin'))) -> dict[str, Any]:
    latest_snapshot = request.app.state.container.asset_manager.snapshot(asset_id=EMS_ASSET_ID).get(EMS_ASSET_ID, {})
    latest_signals = latest_snapshot.get('signals') or {}
    points = _ems_writable_points(request)
    return {
        'asset_id': EMS_ASSET_ID,
        'commands_enabled': request.app.state.container.config.api.commands_enabled,
        'write_access': user.is_internal_admin,
        'count': len(points),
        'items': [_point_to_command(p, latest_signals.get(p.signal_name)) for p in points],
    }


@router.post('/api/commands/ems/write')
async def write_ems_command(
    request: Request,
    body: CommandWriteRequest,
    user: CurrentUser = Depends(require_roles('internal_admin')),
) -> dict[str, Any]:
    return _write_one(request, body, user)


@router.post('/api/commands/ems/batch')
async def write_ems_command_batch(
    request: Request,
    body: CommandBatchWriteRequest,
    user: CurrentUser = Depends(require_roles('internal_admin')),
) -> dict[str, Any]:
    _ensure_commands_enabled(request)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for item in body.writes:
        try:
            results.append(_write_one(request, item, user))
        except HTTPException as exc:
            error = {'signal_name': item.signal_name, 'point_id': item.point_id, 'address': item.address, 'status_code': exc.status_code, 'detail': exc.detail}
            errors.append(error)
            if not body.continue_on_error:
                break
    return {'ok': not errors, 'success_count': len(results), 'error_count': len(errors), 'results': results, 'errors': errors}
