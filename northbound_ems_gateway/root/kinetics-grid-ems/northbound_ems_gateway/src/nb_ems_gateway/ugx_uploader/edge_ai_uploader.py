from __future__ import annotations

import argparse
import json
import logging
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import load_uploader_config
from .ugx_client import UGXTelemetryClient


LOG = logging.getLogger("nb_ems_gateway.ugx_uploader.edge_ai")
_STOP = False


DEFAULT_LATEST_JSON = (
    "/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/"
    "live_inference_v0_3/latest_ml_health_v0_3.json"
)


def _handle_stop(signum: int, frame: Any) -> None:
    global _STOP
    _STOP = True
    LOG.info("stop signal received: %s", signum)


def _parse_iso(ts: str | None):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _age_sec(latest: dict[str, Any]) -> float | None:
    dt = _parse_iso(latest.get("cycle_time"))
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    return round((now - dt.astimezone(timezone.utc)).total_seconds(), 2)


def _status_code(latest: dict[str, Any], stale_after_sec: float) -> int:
    age = _age_sec(latest)
    if age is None or age > stale_after_sec:
        return 0  # stale/no valid recent data

    any_anomaly = any(
        bool(src.get("ml_predicted_anomaly"))
        for src in latest.get("sources", {}).values()
        if isinstance(src, dict)
    )

    return 2 if any_anomaly else 1  # 2=anomaly, 1=normal


def _safe_float(v, default=0.0) -> float:
    try:
        if v is None:
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _safe_bool01(v) -> int:
    return 1 if bool(v) else 0


def build_edge_ai_record(latest: dict[str, Any], *, stale_after_sec: float) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    model_info = latest.get("model_info") or {}

    status_code = _status_code(latest, stale_after_sec)
    latest_age = _age_sec(latest)

    values: dict[str, Any] = {
        "edge_ai_status_code": status_code,
        "edge_ai_any_anomaly": 1 if status_code == 2 else 0,
        "edge_ai_latest_age_sec": _safe_float(latest_age, -1),
        "edge_ai_cycle_index": int(latest.get("cycle_index") or 0),
        "edge_ai_cycle_latency_ms": _safe_float(latest.get("cycle_latency_ms"), 0),
        "edge_ai_feature_count": int(
            model_info.get("feature_count")
            or latest.get("feature_count")
            or 0
        ),
        "edge_ai_threshold": _safe_float(
            model_info.get("threshold")
            or latest.get("threshold")
            or 0
        ),
        "edge_ai_model_isolation_forest": 1,
        "edge_ai_runtime_joblib": 1,
        "edge_ai_preprocessor_standard_scaler": 1,
    }

    for source_id, src in (latest.get("sources") or {}).items():
        if not isinstance(src, dict):
            continue

        bess_id = str(src.get("bess_id") or source_id)
        prefix = f"{bess_id}_edge_ai"

        key_features = src.get("key_features") or {}

        values[f"{prefix}_ok"] = _safe_bool01(src.get("ok"))
        values[f"{prefix}_anomaly"] = _safe_bool01(src.get("ml_predicted_anomaly"))
        values[f"{prefix}_score"] = _safe_float(src.get("anomaly_score_ml"), 0)
        values[f"{prefix}_threshold"] = _safe_float(src.get("threshold"), 0)
        values[f"{prefix}_inference_latency_ms"] = _safe_float(src.get("inference_latency_ms"), 0)

        values[f"{prefix}_bms_cell_voltage_spread"] = _safe_float(
            key_features.get("bms_cell_voltage_spread"), 0
        )
        values[f"{prefix}_bms_temperature_spread"] = _safe_float(
            key_features.get("bms_temperature_spread"), 0
        )
        values[f"{prefix}_bms_fault_flag_count"] = _safe_float(
            key_features.get("bms_fault_flag_count"), 0
        )
        values[f"{prefix}_pcs_fault_flag_count"] = _safe_float(
            key_features.get("pcs_fault_flag_count"), 0
        )
        values[f"{prefix}_pcs_bms_voltage_delta"] = _safe_float(
            key_features.get("pcs_dc_voltage_vs_bms_voltage_delta"), 0
        )
        values[f"{prefix}_pcs_bms_current_delta"] = _safe_float(
            key_features.get("pcs_dc_current_vs_bms_current_delta"), 0
        )
        values[f"{prefix}_pcs_phase_voltage_imbalance"] = _safe_float(
            key_features.get("pcs_phase_voltage_imbalance"), 0
        )
        values[f"{prefix}_pcs_phase_current_imbalance"] = _safe_float(
            key_features.get("pcs_phase_current_imbalance"), 0
        )

    return {
        "ts": int(latest.get("timestamp_epoch_ms") or now_ms),
        "profile": "edge_ai_health_v1",
        "source_id": "edge_ai",
        "bess_id": "edge_ai",
        "values": values,
    }


def load_latest(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"latest Edge AI JSON not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def upload_once(args) -> dict[str, Any]:
    config = load_uploader_config(args.config)

    dry_run = True
    if args.live:
        dry_run = False
    if args.dry_run:
        dry_run = True

    latest = load_latest(args.latest_json)
    record = build_edge_ai_record(latest, stale_after_sec=args.stale_after_sec)

    value_count = len(record.get("values") or {})
    payload_preview = {
        "ts": record["ts"],
        "profile": record["profile"],
        "source_id": record["source_id"],
        "bess_id": record["bess_id"],
        "value_count": value_count,
        "values": record["values"],
    }

    LOG.info("edge_ai_cloud_record=%s", json.dumps(payload_preview, sort_keys=True))

    client = UGXTelemetryClient(config.ugx_server, dry_run=dry_run)
    result = client.post_records([record])

    return {
        "ok": bool(result.get("ok")),
        "dry_run": dry_run,
        "uploaded_records": 1 if result.get("ok") else 0,
        "value_count": value_count,
        "ugx_result": result,
        "record_profile": record["profile"],
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Edge AI health uploader for UGX/Uniqgrid cloud telemetry"
    )
    p.add_argument("--config", default="configs/ugx_cloud_uploader.json")
    p.add_argument("--latest-json", default=DEFAULT_LATEST_JSON)
    p.add_argument("--interval-sec", type=float, default=60.0)
    p.add_argument("--stale-after-sec", type=float, default=180.0)
    p.add_argument("--once", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--live", action="store_true")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    LOG.info(
        "Edge AI UGX uploader started config=%s latest_json=%s interval=%s live=%s dry_run=%s",
        args.config,
        args.latest_json,
        args.interval_sec,
        args.live,
        args.dry_run,
    )

    while not _STOP:
        try:
            result = upload_once(args)
            LOG.info("edge_ai_upload_result=%s", json.dumps(result, sort_keys=True))
        except Exception as exc:
            LOG.exception("edge_ai_upload_failed: %s", exc)

        if args.once:
            break

        time.sleep(max(5.0, float(args.interval_sec)))

    LOG.info("Edge AI UGX uploader stopped")


if __name__ == "__main__":
    main()
