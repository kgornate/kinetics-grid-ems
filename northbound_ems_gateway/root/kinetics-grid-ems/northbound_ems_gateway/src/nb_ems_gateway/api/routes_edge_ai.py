from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException


router = APIRouter(prefix="/api/edge-ai", tags=["edge-ai"])

LATEST_JSON = Path(
    "/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/live_inference_v0_3/latest_ml_health_v0_3.json"
)
JSONL_LOG = Path(
    "/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/live_inference_v0_3/phase7_2_live_inference_v0_3.jsonl"
)
STALE_AFTER_SEC = 60.0


def _parse_iso(ts: str | None):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _load_latest() -> dict[str, Any]:
    if not LATEST_JSON.exists():
        raise HTTPException(
            status_code=503,
            detail={
                "ok": False,
                "error": "latest_ml_health_json_not_found",
                "path": str(LATEST_JSON),
            },
        )

    try:
        return json.loads(LATEST_JSON.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "ok": False,
                "error": "latest_ml_health_json_read_failed",
                "message": repr(exc),
                "path": str(LATEST_JSON),
            },
        )


def _age_sec(latest: dict[str, Any]) -> float | None:
    dt = _parse_iso(latest.get("cycle_time"))
    if dt is None:
        return None

    now = datetime.now(timezone.utc)
    return round((now - dt.astimezone(timezone.utc)).total_seconds(), 2)


def _summary(latest: dict[str, Any]) -> dict[str, Any]:
    age = _age_sec(latest)
    stale = age is None or age > STALE_AFTER_SEC

    sources = {}
    any_anomaly = False

    for source_id, src in latest.get("sources", {}).items():
        pred = bool(src.get("ml_predicted_anomaly"))
        any_anomaly = any_anomaly or pred

        sources[source_id] = {
            "ok": src.get("ok"),
            "source_id": source_id,
            "bess_id": src.get("bess_id"),
            "status": "ANOMALY" if pred else "NORMAL",
            "ml_predicted_anomaly": pred,
            "anomaly_score_ml": src.get("anomaly_score_ml"),
            "threshold": src.get("threshold"),
            "inference_latency_ms": src.get("inference_latency_ms"),
            "key_features": src.get("key_features", {}),
        }

    if stale:
        edge_ai_status = "STALE"
    elif any_anomaly:
        edge_ai_status = "ANOMALY"
    else:
        edge_ai_status = "NORMAL"

    return {
        "ok": bool(latest.get("ok", False)) and not stale,
        "edge_ai_status": edge_ai_status,
        "phase": latest.get("phase"),
        "cycle_time": latest.get("cycle_time"),
        "cycle_index": latest.get("cycle_index"),
        "latest_age_sec": age,
        "stale_after_sec": STALE_AFTER_SEC,
        "cycle_latency_ms": latest.get("cycle_latency_ms"),
        "model_info": latest.get("model_info", {}),
        "sources": sources,
    }


@router.get("/health")
def edge_ai_health():
    latest_exists = LATEST_JSON.exists()

    payload = {
        "ok": True,
        "service": "main-gateway-edge-ai-router",
        "latest_json_exists": latest_exists,
        "latest_json_path": str(LATEST_JSON),
        "jsonl_path": str(JSONL_LOG),
    }

    if latest_exists:
        latest = _load_latest()
        payload.update(
            {
                "edge_ai_status": _summary(latest).get("edge_ai_status"),
                "latest_age_sec": _summary(latest).get("latest_age_sec"),
            }
        )

    return payload


@router.get("/latest")
def edge_ai_latest():
    return _load_latest()


@router.get("/summary")
def edge_ai_summary():
    latest = _load_latest()
    return _summary(latest)


@router.get("/source/{source_id}")
def edge_ai_source(source_id: str):
    latest = _load_latest()
    src = latest.get("sources", {}).get(source_id)

    if src is None:
        raise HTTPException(
            status_code=404,
            detail={
                "ok": False,
                "error": "source_not_found",
                "source_id": source_id,
                "available_sources": sorted(list(latest.get("sources", {}).keys())),
            },
        )

    return src
