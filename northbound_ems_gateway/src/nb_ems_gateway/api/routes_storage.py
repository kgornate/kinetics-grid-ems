from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter()


@router.get("/api/storage/status")
def get_storage_status(request: Request) -> dict:
    container = request.app.state.container
    return container.storage_status()


@router.get("/api/storage/snapshots")
def get_recent_snapshots(
    request: Request,
    asset_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict:
    container = request.app.state.container
    if not container.storage:
        raise HTTPException(status_code=404, detail="Storage is disabled")
    return {
        "asset_id": asset_id,
        "limit": limit,
        "snapshots": container.storage.latest_snapshots(limit=limit, asset_id=asset_id),
    }


@router.get("/api/storage/points")
def get_recent_points(
    request: Request,
    asset_id: str | None = Query(default=None),
    signal_name: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
) -> dict:
    container = request.app.state.container
    if not container.storage:
        raise HTTPException(status_code=404, detail="Storage is disabled")
    return {
        "asset_id": asset_id,
        "signal_name": signal_name,
        "limit": limit,
        "points": container.storage.latest_points(asset_id=asset_id, signal_name=signal_name, limit=limit),
    }
