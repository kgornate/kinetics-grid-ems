from fastapi import APIRouter, Request, HTTPException, Query

router = APIRouter()


def _maybe_expand(container, result: dict, response_format: str) -> dict:
    # V2 stores scalar compact values by default. The same compact data is best
    # for Flutter charts/server pulls. Expanded mode is reserved for compatibility
    # if a future client needs additional presentation metadata.
    if response_format == 'expanded' and container.fast_bess_logger:
        result = dict(result)
        result['items'] = [container.fast_bess_logger.expand_item(dict(item)) for item in result.get('items', [])]
    return result


@router.get('/api/fast-bess/status')
def fast_bess_status(request: Request) -> dict:
    c = request.app.state.container
    return c.fast_bess_logger_status()


@router.get('/api/fast-bess/profile')
def fast_bess_profile(request: Request) -> dict:
    c = request.app.state.container
    if not c.fast_bess_logger:
        return {'enabled': False, 'profile': None}
    return c.fast_bess_logger.profile_status()


@router.get('/api/fast-bess/live')
def fast_bess_live(request: Request) -> dict:
    """Return S1-ready PCS/BMS values directly from the live AssetManager cache.

    This endpoint does not query SQLite and does not trigger Modbus reads.
    """
    c = request.app.state.container
    if not c.fast_bess_logger:
        raise HTTPException(503, 'fast BESS profile unavailable')
    try:
        return c.fast_bess_logger.live_snapshot()
    except Exception as exc:
        raise HTTPException(503, f'live fast BESS snapshot unavailable: {exc}') from exc


@router.get('/api/fast-bess/latest')
def fast_bess_latest(
    request: Request,
    format: str = Query('compact', pattern='^(compact|expanded)$'),
) -> dict:
    c = request.app.state.container
    if not c.storage:
        raise HTTPException(503, 'storage disabled')
    return _maybe_expand(c, c.storage.latest_fast_bess_samples(), format)


@router.get('/api/fast-bess/history')
def fast_bess_history(
    request: Request,
    source_id: str | None = None,
    limit: int = 100,
    from_epoch_ms: int | None = None,
    to_epoch_ms: int | None = None,
    order: str = 'desc',
    format: str = Query('compact', pattern='^(compact|expanded)$'),
) -> dict:
    c = request.app.state.container
    if not c.storage:
        raise HTTPException(503, 'storage disabled')
    result = c.storage.query_fast_bess_samples(
        source_id=source_id,
        limit=max(1, min(limit, 5000)),
        from_epoch_ms=from_epoch_ms,
        to_epoch_ms=to_epoch_ms,
        order=order,
    )
    return _maybe_expand(c, result, format)
