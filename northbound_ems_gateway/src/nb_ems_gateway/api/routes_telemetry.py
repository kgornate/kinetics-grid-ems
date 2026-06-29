from __future__ import annotations

from fastapi import APIRouter, Query, Request

router = APIRouter()


@router.get("/api/telemetry")
def get_all_telemetry(
    request: Request,
    include_empty_assets: bool = Query(default=True),
) -> dict:
    container = request.app.state.container
    snapshot = container.asset_manager.telemetry_snapshot()
    if not include_empty_assets:
        snapshot = {
            asset_id: asset
            for asset_id, asset in snapshot.items()
            if asset.get("signal_count", 0) > 0
        }
    return {
        "gateway_id": container.config.gateway.id,
        "mode": container.config.gateway.mode,
        "assets": snapshot,
    }


@router.get("/api/telemetry/key-signals")
def get_all_key_signals(request: Request) -> dict:
    container = request.app.state.container
    return {
        "gateway_id": container.config.gateway.id,
        "assets": {
            asset_id: asset.get("key_signals", {})
            for asset_id, asset in container.asset_manager.telemetry_snapshot().items()
        },
    }
