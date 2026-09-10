#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


def load_feature_list(ml_dir: Path):
    p = ml_dir / "feature_list_v0_3.json"
    with open(p, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload["features"]


def load_xy(csv_path: Path, features):
    df = pd.read_csv(csv_path)
    x = df[features].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
    return df, x


def score_model(model, scaler, x):
    xs = scaler.transform(x)
    raw = model.score_samples(xs)

    # IsolationForest gives higher score for normal samples.
    # We invert it so higher anomaly_score_ml means more abnormal.
    anomaly_score = -raw
    return anomaly_score


def summarize_scores(name, scores, threshold):
    scores = np.asarray(scores)
    return {
        "dataset": name,
        "rows": int(len(scores)),
        "threshold": float(threshold),
        "predicted_anomaly_rows": int((scores >= threshold).sum()),
        "predicted_anomaly_percent": float(((scores >= threshold).mean() * 100.0) if len(scores) else 0.0),
        "score_min": float(scores.min()) if len(scores) else None,
        "score_p50": float(np.percentile(scores, 50)) if len(scores) else None,
        "score_p90": float(np.percentile(scores, 90)) if len(scores) else None,
        "score_p95": float(np.percentile(scores, 95)) if len(scores) else None,
        "score_p99": float(np.percentile(scores, 99)) if len(scores) else None,
        "score_max": float(scores.max()) if len(scores) else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ml-dir", required=True, help="Path to ml_v0_3 directory")
    ap.add_argument("--out-dir", required=True, help="Output directory for model artifacts")
    ap.add_argument("--n-estimators", type=int, default=200)
    ap.add_argument("--max-samples", type=int, default=8192)
    ap.add_argument("--contamination", type=float, default=0.005)
    ap.add_argument("--threshold-percentile", type=float, default=99.5)
    args = ap.parse_args()

    ml_dir = Path(args.ml_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    features = load_feature_list(ml_dir)

    train_csv = ml_dir / "normal_train_v0_3.csv"
    val_csv = ml_dir / "normal_validation_v0_3.csv"
    normal_test_csv = ml_dir / "normal_test_sample_v0_3.csv"
    anomaly_test_csv = ml_dir / "warning_abnormal_test_v0_3.csv"
    dq_test_csv = ml_dir / "data_quality_test_v0_3.csv"

    print("PHASE 6: TRAIN ML BASELINE")
    print("ML_DIR =", ml_dir)
    print("OUT_DIR =", out_dir)
    print("FEATURE_COUNT =", len(features))
    print("FEATURES =", features)

    print("Loading train data...")
    train_df, x_train = load_xy(train_csv, features)

    print("Loading validation/test data...")
    val_df, x_val = load_xy(val_csv, features)
    normal_test_df, x_normal_test = load_xy(normal_test_csv, features)
    anomaly_test_df, x_anomaly_test = load_xy(anomaly_test_csv, features)

    if dq_test_csv.exists():
        try:
            dq_df, x_dq = load_xy(dq_test_csv, features)
        except Exception:
            dq_df, x_dq = pd.DataFrame(), pd.DataFrame(columns=features)
    else:
        dq_df, x_dq = pd.DataFrame(), pd.DataFrame(columns=features)

    print("TRAIN_ROWS =", len(x_train))
    print("VAL_ROWS =", len(x_val))
    print("NORMAL_TEST_ROWS =", len(x_normal_test))
    print("ANOMALY_TEST_ROWS =", len(x_anomaly_test))
    print("DATA_QUALITY_TEST_ROWS =", len(x_dq))

    print("Fitting StandardScaler...")
    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)

    print("Training IsolationForest...")
    model = IsolationForest(
        n_estimators=args.n_estimators,
        max_samples=args.max_samples,
        contamination=args.contamination,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(x_train_scaled)

    print("Scoring validation/test datasets...")
    train_scores = score_model(model, scaler, x_train)
    val_scores = score_model(model, scaler, x_val)
    normal_test_scores = score_model(model, scaler, x_normal_test)
    anomaly_test_scores = score_model(model, scaler, x_anomaly_test)

    if len(x_dq):
        dq_scores = score_model(model, scaler, x_dq)
    else:
        dq_scores = np.array([])

    # Threshold is set from clean normal validation data.
    threshold = float(np.percentile(val_scores, args.threshold_percentile))

    reports = [
        summarize_scores("normal_train", train_scores, threshold),
        summarize_scores("normal_validation", val_scores, threshold),
        summarize_scores("normal_test", normal_test_scores, threshold),
        summarize_scores("warning_abnormal_test", anomaly_test_scores, threshold),
        summarize_scores("data_quality_test", dq_scores, threshold),
    ]

    report_payload = {
        "phase": "EAI_PHASE_6_ML_BASELINE",
        "model_type": "StandardScaler + IsolationForest",
        "ml_dir": str(ml_dir),
        "out_dir": str(out_dir),
        "feature_count": len(features),
        "features": features,
        "training_rows": int(len(x_train)),
        "validation_rows": int(len(x_val)),
        "threshold_source": "normal_validation",
        "threshold_percentile": args.threshold_percentile,
        "anomaly_threshold": threshold,
        "model_params": {
            "n_estimators": args.n_estimators,
            "max_samples": args.max_samples,
            "contamination": args.contamination,
            "random_state": 42,
        },
        "reports": reports,
    }

    model_path = out_dir / "iforest_model_v0_3.joblib"
    scaler_path = out_dir / "standard_scaler_v0_3.joblib"
    report_path = out_dir / "phase6_training_report_v0_3.json"
    manifest_path = out_dir / "ml_model_manifest_v0_3.json"

    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)

    scaler_json = {
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "var": scaler.var_.tolist(),
    }

    manifest = {
        "version": "v0_3",
        "model_type": "isolation_forest",
        "model_file": str(model_path.name),
        "scaler_file": str(scaler_path.name),
        "feature_count": len(features),
        "features": features,
        "threshold": threshold,
        "threshold_direction": "anomaly_score_ml >= threshold means anomaly",
        "scaler": scaler_json,
        "notes": [
            "This is the first ML baseline model.",
            "It is suitable for PC/gateway CPU inference experiments.",
            "For NPU/TFLite/eIQ deployment, train a small neural-network autoencoder later.",
        ],
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2)

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    pd.DataFrame(reports).to_csv(out_dir / "phase6_score_summary_v0_3.csv", index=False)

    anomaly_preview = anomaly_test_df.copy()
    anomaly_preview["anomaly_score_ml"] = anomaly_test_scores
    anomaly_preview["ml_predicted_anomaly"] = anomaly_preview["anomaly_score_ml"] >= threshold
    anomaly_preview.sort_values("anomaly_score_ml", ascending=False).head(500).to_csv(
        out_dir / "phase6_top_warning_abnormal_scores_v0_3.csv",
        index=False,
    )

    print("===== PHASE 6 TRAINING COMPLETE =====")
    print(json.dumps(report_payload, indent=2))
    print()
    print("MODEL_PATH =", model_path)
    print("SCALER_PATH =", scaler_path)
    print("REPORT_PATH =", report_path)
    print("MANIFEST_PATH =", manifest_path)


if __name__ == "__main__":
    main()
