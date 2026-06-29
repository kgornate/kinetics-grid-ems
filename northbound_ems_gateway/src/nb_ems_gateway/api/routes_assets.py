from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter()


@router.get("/api/assets")
def list_assets(request: Request) -> dict:
    container = request.app.state.container
    return {"assets": container.asset_manager.list_assets()}


@router.get("/api/assets/{asset_id}")
def get_asset(asset_id: str, request: Request) -> dict:
    container = request.app.state.container
    asset = container.asset_manager.get_asset(asset_id, include_telemetry=False)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset_id: {asset_id}")
    return asset


@router.get("/api/assets/{asset_id}/telemetry")
def get_asset_telemetry(
    asset_id: str,
    request: Request,
    category: str | None = Query(default=None, description="Optional telemetry category filter."),
) -> dict:
    container = request.app.state.container
    asset = container.asset_manager.get_asset(asset_id, include_telemetry=True, category=category)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset_id: {asset_id}")
    asset["category_filter"] = category
    return asset


@router.get("/api/assets/{asset_id}/key-signals")
def get_asset_key_signals(asset_id: str, request: Request) -> dict:
    container = request.app.state.container
    asset = container.asset_manager.get_asset(asset_id, include_telemetry=False)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset_id: {asset_id}")
    return {
        "asset_id": asset_id,
        "display_name": asset["display_name"],
        "online": asset["online"],
        "last_update_utc": asset["last_update_utc"],
        "key_signals": asset.get("key_signals", {}),
    }
