#!/usr/bin/env python3

import argparse
import csv
import json
from pathlib import Path

import joblib
import numpy as np


def to_float(value):
    if value is None or value == "":
        raise ValueError("empty")
    return float(value)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    model_dir = Path(args.model_dir)

    manifest_path = model_dir / "ml_model_manifest_v0_3.json"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    features = manifest["features"]
    threshold = float(manifest["threshold"])

    model = joblib.load(model_dir / manifest["model_file"])
    scaler = joblib.load(model_dir / manifest["scaler_file"])

    rows = []
    x_rows = []
    valid_indexes = []

    with open(args.input, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])

        for idx, row in enumerate(reader):
            rows.append(row)

            try:
                values = [to_float(row.get(k, "")) for k in features]
                x_rows.append(values)
                valid_indexes.append(idx)
            except Exception:
                row["ml_numeric_complete"] = "false"
                row["anomaly_score_ml"] = ""
                row["ml_predicted_anomaly"] = "false"

    if x_rows:
        x = np.array(x_rows, dtype=float)
        xs = scaler.transform(x)
        raw_scores = model.score_samples(xs)
        anomaly_scores = -raw_scores

        for idx, score in zip(valid_indexes, anomaly_scores):
            rows[idx]["ml_numeric_complete"] = "true"
            rows[idx]["anomaly_score_ml"] = round(float(score), 6)
            rows[idx]["ml_predicted_anomaly"] = "true" if float(score) >= threshold else "false"

    output_fields = fieldnames[:]
    for col in ["ml_numeric_complete", "anomaly_score_ml", "ml_predicted_anomaly"]:
        if col not in output_fields:
            output_fields.append(col)

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    complete = sum(1 for r in rows if r.get("ml_numeric_complete") == "true")
    predicted = sum(1 for r in rows if r.get("ml_predicted_anomaly") == "true")

    print("===== PHASE 7 OFFLINE INFERENCE COMPLETE =====")
    print("MODEL_DIR =", model_dir)
    print("INPUT =", args.input)
    print("OUTPUT =", args.output)
    print("FEATURE_COUNT =", len(features))
    print("THRESHOLD =", threshold)
    print("TOTAL_ROWS =", total)
    print("NUMERIC_COMPLETE_ROWS =", complete)
    print("ML_PREDICTED_ANOMALY_ROWS =", predicted)
    print("ML_PREDICTED_ANOMALY_PERCENT =", round((predicted / total * 100.0) if total else 0.0, 3))


if __name__ == "__main__":
    main()
