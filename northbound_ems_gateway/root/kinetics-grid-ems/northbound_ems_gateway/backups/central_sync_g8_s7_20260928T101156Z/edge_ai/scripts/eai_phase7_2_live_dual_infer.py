#!/usr/bin/env python3

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import joblib

warnings.filterwarnings("ignore", message="X does not have valid feature names.*")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eai_phase7_1_live_api_infer import login, run_once


def atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def rotate_jsonl_if_needed(path, max_mb):
    path = Path(path)
    if not path.exists():
        return

    max_bytes = int(max_mb * 1024 * 1024)
    if path.stat().st_size < max_bytes:
        return

    rotated = path.with_suffix(path.suffix + ".1")
    if rotated.exists():
        rotated.unlink()
    path.rename(rotated)


def status_text(pred):
    return "ANOMALY" if pred else "NORMAL"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--username", default="internal")
    ap.add_argument("--password-env", default="NB_EMS_INTERNAL_PASSWORD")
    ap.add_argument("--model-dir", default="model")
    ap.add_argument("--sources", default="external_ems_1,external_ems_2")
    ap.add_argument("--interval-sec", type=float, default=5.0)
    ap.add_argument("--jsonl", default="/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/live_inference_v0_3/phase7_2_live_inference_v0_3.jsonl")
    ap.add_argument("--latest-json", default="/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/live_inference_v0_3/latest_ml_health_v0_3.json")
    ap.add_argument("--max-jsonl-mb", type=float, default=50.0)
    args = ap.parse_args()

    password = os.environ.get(args.password_env)
    if not password:
        raise SystemExit(f"Missing env var: {args.password_env}")

    model_dir = Path(args.model_dir)

    with open(model_dir / "ml_model_manifest_v0_3.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)

    model = joblib.load(model_dir / manifest["model_file"])
    scaler = joblib.load(model_dir / manifest["scaler_file"])

    token = login(args.base_url, args.username, password)
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]

    Path(args.jsonl).parent.mkdir(parents=True, exist_ok=True)
    Path(args.latest_json).parent.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now().astimezone().isoformat()
    cycle_index = 0

    model_info = {
        "model_type": "IsolationForest",
        "runtime_format": "joblib",
        "preprocessor": "StandardScaler",
        "model_file": manifest.get("model_file"),
        "scaler_file": manifest.get("scaler_file"),
        "feature_count": len(manifest["features"]),
        "threshold": float(manifest["threshold"]),
        "model_dir": str(model_dir),
    }

    print("==============================================================")
    print(" PHASE 8 HARDENED LIVE EDGE AI INFERENCE")
    print(" Live PCS/BMS telemetry -> 33 features -> ML anomaly score")
    print("==============================================================")
    print("BASE_URL       =", args.base_url)
    print("SOURCES        =", ", ".join(sources))
    print("FEATURE_COUNT  =", model_info["feature_count"])
    print("THRESHOLD      =", model_info["threshold"])
    print("JSONL_LOG      =", args.jsonl)
    print("LATEST_JSON    =", args.latest_json)
    print("INTERVAL_SEC   =", args.interval_sec)
    print("MAX_JSONL_MB   =", args.max_jsonl_mb)
    print("STARTED_AT     =", started_at)
    print("==============================================================")

    while True:
        cycle_index += 1
        cycle_start = time.perf_counter()
        cycle_time = datetime.now().astimezone().isoformat()

        latest = {
            "ok": True,
            "phase": "8",
            "cycle_index": cycle_index,
            "cycle_time": cycle_time,
            "started_at": started_at,
            "model_info": model_info,
            "sources": {},
        }

        print("")
        print(f"[{cycle_time}] live inference cycle #{cycle_index}")

        rotate_jsonl_if_needed(args.jsonl, args.max_jsonl_mb)

        for source in sources:
            source_start = time.perf_counter()

            one_args = SimpleNamespace(
                base_url=args.base_url,
                source_id=source,
            )

            result = run_once(one_args, model, scaler, manifest, token)

            source_latency_ms = round((time.perf_counter() - source_start) * 1000, 2)

            result["cycle_time"] = cycle_time
            result["cycle_index"] = cycle_index
            result["phase"] = "8"
            result["inference_latency_ms"] = source_latency_ms
            result["model_info"] = model_info

            with open(args.jsonl, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, sort_keys=True) + "\n")

            latest["sources"][source] = result

            if result.get("ok"):
                print(
                    f"  {source:14s} | {result['bess_id']:6s} | "
                    f"score={result['anomaly_score_ml']:.6f} | "
                    f"threshold={result['threshold']:.6f} | "
                    f"status={status_text(result['ml_predicted_anomaly'])} | "
                    f"latency={source_latency_ms} ms"
                )
            else:
                latest["ok"] = False
                print(f"  {source:14s} | ERROR | latency={source_latency_ms} ms | {result.get('error')}")

        cycle_latency_ms = round((time.perf_counter() - cycle_start) * 1000, 2)
        latest["cycle_latency_ms"] = cycle_latency_ms

        atomic_write_json(args.latest_json, latest)

        print(f"  cycle_latency={cycle_latency_ms} ms")

        sleep_time = max(0.0, args.interval_sec - (time.perf_counter() - cycle_start))
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
