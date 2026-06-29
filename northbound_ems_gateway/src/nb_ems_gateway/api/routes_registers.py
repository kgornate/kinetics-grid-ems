from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Query, Request

router = APIRouter()


@router.get("/api/registers/map")
def get_register_map_summary(request: Request) -> dict:
    register_map = request.app.state.container.register_map
    assets = Counter(p.asset_id or "unknown" for p in register_map.points)
    poll_groups = Counter(p.poll_group for p in register_map.points)
    categories = Counter(p.category or "general" for p in register_map.points)
    key_signals = [p.to_dict() for p in register_map.points if p.is_key_signal]
    return {
        "name": register_map.name,
        "version": register_map.version,
        "point_count": register_map.point_count,
        "min_address": register_map.min_address,
        "max_address": register_map.max_address,
        "entities": register_map.entities(),
        "assets": dict(sorted(assets.items())),
        "poll_groups": dict(sorted(poll_groups.items())),
        "categories": dict(sorted(categories.items())),
        "key_signal_count": len(key_signals),
        "key_signals": key_signals,
    }


@router.get("/api/registers/raw")
def get_register_points(
    request: Request,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    asset_id: str | None = Query(default=None),
    category: str | None = Query(default=None),
    key_only: bool = Query(default=False),
) -> dict:
    register_map = request.app.state.container.register_map
    points = list(register_map.points)
    if asset_id:
        points = [point for point in points if point.asset_id == asset_id]
    if category:
        points = [point for point in points if (point.category or "general") == category]
    if key_only:
        points = [point for point in points if point.is_key_signal]
    page = points[offset:offset + limit]
    return {
        "total": len(points),
        "offset": offset,
        "limit": limit,
        "asset_id": asset_id,
        "category": category,
        "key_only": key_only,
        "points": [point.to_dict() for point in page],
    }
