#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
from collections import Counter

import joblib
import numpy as np
import pandas as pd


def load_manifest(model_dir: Path):
    p = model_dir / "ml_model_manifest_v0_3.json"
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def reason_categories(reason: str):
    r = str(reason or "").lower()
    cats = []

    if "pcs phase current imbalance" in r:
        cats.append("pcs_phase_current_imbalance")
    if "pcs phase voltage imbalance" in r:
        cats.append("pcs_phase_voltage_imbalance")
    if "pcs dc current and bms current mismatch" in r:
        cats.append("pcs_bms_current_mismatch")
    if "pcs dc voltage and bms voltage mismatch" in r:
        cats.append("pcs_bms_voltage_mismatch")
    if "bms cell voltage spread" in r:
        cats.append("bms_cell_voltage_spread")
    if "bms temperature spread" in r:
        cats.append("bms_temperature_spread")
    if "pcs fault" in r or "alarm flags" in r:
        cats.append("pcs_fault_or_alarm")
    if "telemetry quality" in r or "data_quality" in r:
        cats.append("data_quality")
    if "soc" in r:
        cats.append("soc_mismatch")

    return cats or ["other"]


def score_df(df, features, scaler, model, threshold):
    x = df[features].astype(float).replace([np.inf, -np.inf], np.nan)
    valid_mask = x.notna().all(axis=1)

    out = df.copy()
    out["ml_numeric_complete"] = valid_mask

    scores = np.full(len(out), np.nan)

    if valid_mask.any():
        xs = scaler.transform(x.loc[valid_mask])
        raw = model.score_samples(xs)
        scores[valid_mask.to_numpy()] = -raw

    out["anomaly_score_ml"] = scores
    out["ml_predicted_anomaly"] = out["anomaly_score_ml"] >= threshold
    return out


def dataset_summary(name, df, threshold):
    valid = df["anomaly_score_ml"].dropna()
    if len(valid) == 0:
        return {
            "dataset": name,
            "rows": len(df),
            "numeric_complete_rows": 0,
            "threshold": threshold,
            "ml_predicted_anomaly_rows": 0,
            "ml_predicted_anomaly_percent": 0,
        }

    return {
        "dataset": name,
        "rows": int(len(df)),
        "numeric_complete_rows": int(df["ml_numeric_complete"].sum()),
        "threshold": float(threshold),
        "ml_predicted_anomaly_rows": int(df["ml_predicted_anomaly"].sum()),
        "ml_predicted_anomaly_percent": float(df["ml_predicted_anomaly"].mean() * 100.0),
        "score_min": float(valid.min()),
        "score_p50": float(np.percentile(valid, 50)),
        "score_p90": float(np.percentile(valid, 90)),
        "score_p95": float(np.percentile(valid, 95)),
        "score_p99": float(np.percentile(valid, 99)),
        "score_max": float(valid.max()),
    }


def build_reason_category_summary(df):
    rows = []
    for _, row in df.iterrows():
        cats = reason_categories(row.get("anomaly_reason", ""))
        for cat in cats:
            rows.append({
                "reason_category": cat,
                "health_state": row.get("health_state", ""),
                "source_id": row.get("source_id", ""),
                "bess_id": row.get("bess_id", ""),
                "ml_predicted_anomaly": bool(row.get("ml_predicted_anomaly", False)),
                "anomaly_score_ml": row.get("anomaly_score_ml", np.nan),
            })

    if not rows:
        return pd.DataFrame()

    cdf = pd.DataFrame(rows)

    out_rows = []
    for cat, g in cdf.groupby("reason_category"):
        total = len(g)
        ml = int(g["ml_predicted_anomaly"].sum())
        out_rows.append({
            "reason_category": cat,
            "total_rows": total,
            "ml_detected_rows": ml,
            "ml_detected_percent": (ml / total * 100.0) if total else 0.0,
            "score_avg": float(g["anomaly_score_ml"].mean()),
            "score_max": float(g["anomaly_score_ml"].max()),
        })

    return pd.DataFrame(out_rows).sort_values(
        ["ml_detected_rows", "score_max"],
        ascending=False,
    )


def build_source_bess_summary(df):
    rows = []
    group_cols = ["source_id", "bess_id", "health_state"]

    for key, g in df.groupby(group_cols):
        total = len(g)
        ml = int(g["ml_predicted_anomaly"].sum())
        rows.append({
            "source_id": key[0],
            "bess_id": key[1],
            "health_state": key[2],
            "total_rows": total,
            "ml_detected_rows": ml,
            "ml_detected_percent": (ml / total * 100.0) if total else 0.0,
            "score_avg": float(g["anomaly_score_ml"].mean()),
            "score_max": float(g["anomaly_score_ml"].max()),
        })

    return pd.DataFrame(rows).sort_values(
        ["source_id", "bess_id", "health_state"]
    )


def build_ml_event_windows(df, gap_sec=30):
    mdf = df[df["ml_predicted_anomaly"] == True].copy()

    if mdf.empty:
        return pd.DataFrame()

    mdf["timestamp_dt"] = pd.to_datetime(mdf["timestamp_utc"], utc=True, errors="coerce")
    mdf = mdf.dropna(subset=["timestamp_dt"])
    mdf = mdf.sort_values(["source_id", "bess_id", "timestamp_dt"])

    events = []
    event_id = 0

    for (source, bess), g in mdf.groupby(["source_id", "bess_id"]):
        current = None

        for _, row in g.iterrows():
            ts = row["timestamp_dt"]

            cats = reason_categories(row.get("anomaly_reason", ""))

            if current is None:
                current = {
                    "source_id": source,
                    "bess_id": bess,
                    "start_utc": ts,
                    "end_utc": ts,
                    "row_count": 1,
                    "max_ml_score": float(row["anomaly_score_ml"]),
                    "max_rule_score": float(row.get("anomaly_score", 0) or 0),
                    "health_states": Counter([row.get("health_state", "")]),
                    "categories": Counter(cats),
                    "top_reason": row.get("anomaly_reason", ""),
                }
                continue

            gap = (ts - current["end_utc"]).total_seconds()

            if gap <= gap_sec:
                current["end_utc"] = ts
                current["row_count"] += 1
                current["max_ml_score"] = max(current["max_ml_score"], float(row["anomaly_score_ml"]))
                current["max_rule_score"] = max(current["max_rule_score"], float(row.get("anomaly_score", 0) or 0))
                current["health_states"][row.get("health_state", "")] += 1
                for c in cats:
                    current["categories"][c] += 1
            else:
                event_id += 1
                events.append(finalize_event(event_id, current))
                current = {
                    "source_id": source,
                    "bess_id": bess,
                    "start_utc": ts,
                    "end_utc": ts,
                    "row_count": 1,
                    "max_ml_score": float(row["anomaly_score_ml"]),
                    "max_rule_score": float(row.get("anomaly_score", 0) or 0),
                    "health_states": Counter([row.get("health_state", "")]),
                    "categories": Counter(cats),
                    "top_reason": row.get("anomaly_reason", ""),
                }

        if current is not None:
            event_id += 1
            events.append(finalize_event(event_id, current))

    return pd.DataFrame(events).sort_values("max_ml_score", ascending=False)


def finalize_event(event_id, ev):
    duration_sec = (ev["end_utc"] - ev["start_utc"]).total_seconds()

    return {
        "ml_event_id": event_id,
        "source_id": ev["source_id"],
        "bess_id": ev["bess_id"],
        "start_utc": ev["start_utc"].isoformat(),
        "end_utc": ev["end_utc"].isoformat(),
        "duration_sec": round(duration_sec, 3),
        "row_count": ev["row_count"],
        "max_ml_score": round(ev["max_ml_score"], 6),
        "max_rule_score": round(ev["max_rule_score"], 6),
        "dominant_health_state": ev["health_states"].most_common(1)[0][0],
        "top_categories": ";".join([k for k, _ in ev["categories"].most_common(5)]),
        "top_reason": ev["top_reason"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ml-dir", required=True)
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    ml_dir = Path(args.ml_dir)
    model_dir = Path(args.model_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(model_dir)
    features = manifest["features"]
    threshold = float(manifest["threshold"])

    model = joblib.load(model_dir / manifest["model_file"])
    scaler = joblib.load(model_dir / manifest["scaler_file"])

    datasets = {
        "normal_validation": ml_dir / "normal_validation_v0_3.csv",
        "normal_test": ml_dir / "normal_test_sample_v0_3.csv",
        "warning_abnormal_test": ml_dir / "warning_abnormal_test_v0_3.csv",
        "data_quality_test": ml_dir / "data_quality_test_v0_3.csv",
    }

    scored = {}
    summaries = []

    for name, path in datasets.items():
        print("Scoring", name, "from", path)
        df = pd.read_csv(path)
        sdf = score_df(df, features, scaler, model, threshold)
        scored[name] = sdf
        summaries.append(dataset_summary(name, sdf, threshold))
        sdf.to_csv(out_dir / f"{name}_ml_scored_v0_3.csv", index=False)

    warning_df = scored["warning_abnormal_test"]

    reason_summary = build_reason_category_summary(warning_df)
    source_bess_summary = build_source_bess_summary(warning_df)
    ml_events = build_ml_event_windows(warning_df, gap_sec=30)

    top_ml = warning_df.sort_values("anomaly_score_ml", ascending=False).head(300)
    rule_abnormal = warning_df[warning_df["health_state"] == "abnormal"].sort_values(
        "anomaly_score_ml",
        ascending=False,
    )

    pd.DataFrame(summaries).to_csv(out_dir / "phase6_2_dataset_score_summary.csv", index=False)
    reason_summary.to_csv(out_dir / "phase6_2_reason_category_summary.csv", index=False)
    source_bess_summary.to_csv(out_dir / "phase6_2_source_bess_summary.csv", index=False)
    ml_events.to_csv(out_dir / "phase6_2_ml_event_windows.csv", index=False)
    top_ml.to_csv(out_dir / "phase6_2_top_ml_anomalies.csv", index=False)
    rule_abnormal.to_csv(out_dir / "phase6_2_rule_abnormal_rows_with_ml.csv", index=False)

    findings = {
        "phase": "EAI_PHASE_6_2_MODEL_VALIDATION",
        "threshold": threshold,
        "feature_count": len(features),
        "outputs": str(out_dir),
        "dataset_summaries": summaries,
        "warning_abnormal_rows": int(len(warning_df)),
        "warning_abnormal_ml_detected_rows": int(warning_df["ml_predicted_anomaly"].sum()),
        "warning_abnormal_ml_detected_percent": float(warning_df["ml_predicted_anomaly"].mean() * 100.0),
        "rule_abnormal_rows": int((warning_df["health_state"] == "abnormal").sum()),
        "rule_abnormal_ml_detected_rows": int(rule_abnormal["ml_predicted_anomaly"].sum()) if not rule_abnormal.empty else 0,
        "ml_event_windows": int(len(ml_events)),
        "top_reason_categories": reason_summary.head(10).to_dict(orient="records") if not reason_summary.empty else [],
        "top_source_bess_summary": source_bess_summary.to_dict(orient="records") if not source_bess_summary.empty else [],
        "top_ml_events": ml_events.head(10).to_dict(orient="records") if not ml_events.empty else [],
    }

    with open(out_dir / "phase6_2_validation_report.json", "w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2)

    lines = []
    lines.append("===== PHASE 6.2 KEY FINDINGS =====")
    lines.append(f"Threshold = {threshold}")
    lines.append(f"Feature count = {len(features)}")
    lines.append("")
    lines.append("DATASET SUMMARY")
    for s in summaries:
        lines.append(
            f"{s['dataset']}: rows={s['rows']}, ml_anomaly_rows={s['ml_predicted_anomaly_rows']}, "
            f"ml_anomaly_percent={round(s['ml_predicted_anomaly_percent'], 3)}"
        )
    lines.append("")
    lines.append("WARNING/ABNORMAL OVERLAP")
    lines.append(f"warning_abnormal_rows = {findings['warning_abnormal_rows']}")
    lines.append(f"warning_abnormal_ml_detected_rows = {findings['warning_abnormal_ml_detected_rows']}")
    lines.append(f"warning_abnormal_ml_detected_percent = {round(findings['warning_abnormal_ml_detected_percent'], 3)}")
    lines.append(f"rule_abnormal_rows = {findings['rule_abnormal_rows']}")
    lines.append(f"rule_abnormal_ml_detected_rows = {findings['rule_abnormal_ml_detected_rows']}")
    lines.append(f"ml_event_windows = {findings['ml_event_windows']}")
    lines.append("")
    lines.append("TOP REASON CATEGORIES")
    if not reason_summary.empty:
        for _, r in reason_summary.head(10).iterrows():
            lines.append(
                f"{r['reason_category']}: total={int(r['total_rows'])}, "
                f"ml_detected={int(r['ml_detected_rows'])}, "
                f"ml_percent={round(float(r['ml_detected_percent']), 2)}, "
                f"max_score={round(float(r['score_max']), 4)}"
            )
    lines.append("")
    lines.append("TOP ML EVENTS")
    if not ml_events.empty:
        for _, r in ml_events.head(10).iterrows():
            lines.append(
                f"{r['source_id']} {r['bess_id']} {r['start_utc']} to {r['end_utc']} "
                f"rows={int(r['row_count'])} max_ml={r['max_ml_score']} cats={r['top_categories']}"
            )

    text = "\n".join(lines)
    (out_dir / "phase6_2_key_findings.txt").write_text(text, encoding="utf-8")

    print(text)
    print("")
    print("PHASE 6.2 COMPLETE")
    print("OUT_DIR =", out_dir)


if __name__ == "__main__":
    main()
