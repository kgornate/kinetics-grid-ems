#!/usr/bin/env python3

import csv
import json
import math
from pathlib import Path

INPUT = "/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/data/bess_anomaly_scored_v0_3_full_10d.csv"
OUTDIR = Path("/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/data/ml_v0_3")
LOG = Path("/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/logs/eai_phase5_prepare_ml_datasets.log")

OUTDIR.mkdir(parents=True, exist_ok=True)

TRAIN = OUTDIR / "normal_train_v0_3.csv"
VAL = OUTDIR / "normal_validation_v0_3.csv"
NORMAL_TEST = OUTDIR / "normal_test_sample_v0_3.csv"
ANOMALY_TEST = OUTDIR / "warning_abnormal_test_v0_3.csv"
DATA_QUALITY_TEST = OUTDIR / "data_quality_test_v0_3.csv"
FEATURE_LIST = OUTDIR / "feature_list_v0_3.json"
SCALER = OUTDIR / "scaler_config_v0_3.json"
SUMMARY = OUTDIR / "ml_dataset_summary_v0_3.json"

MAX_TRAIN = 300000
MAX_VAL = 80000
MAX_NORMAL_TEST = 50000
MAX_ANOMALY_TEST = 200000
MAX_DATA_QUALITY_TEST = 50000

FEATURE_CANDIDATES = [
    "pcs_phase_voltage_imbalance",
    "pcs_phase_current_imbalance",
    "pcs_dc_voltage_vs_bms_voltage_delta",
    "pcs_dc_current_vs_bms_current_delta",
    "pcs_soc_vs_bms_soc_delta",
    "bms_temperature_spread",
    "bms_cell_voltage_spread",
    "pcs_phase_a_voltage",
    "pcs_phase_b_voltage",
    "pcs_phase_c_voltage",
    "pcs_phase_a_current",
    "pcs_phase_b_current",
    "pcs_phase_c_current",
    "pcs_dc_voltage",
    "pcs_dc_current",
    "pcs_grid_frequency",
    "pcs_charge_discharge_power",
    "pcs_total_active_power",
    "pcs_soc",
    "bms_cluster_total_voltage",
    "bms_cluster_total_current",
    "bms_can_hall_sampling_current",
    "bms_display_soc",
    "bms_soh",
    "bms_cell_max_voltage",
    "bms_cell_min_voltage",
    "bms_battery_max_temperature",
    "bms_battery_min_temperature",
    "bms_average_temperature",
    "bms_insulation_resistance",
    "bms_pre_charge_total_voltage",
    "pcs_fault_flag_count",
    "bms_fault_flag_count",
]

META = [
    "id",
    "timestamp_utc",
    "source_id",
    "bess_id",
    "quality",
    "anomaly_score",
    "health_state",
    "anomaly_reason",
]


class Stats:
    def __init__(self):
        self.n = 0
        self.mean = 0.0
        self.m2 = 0.0
        self.min = None
        self.max = None

    def add(self, x):
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        delta2 = x - self.mean
        self.m2 += delta * delta2
        self.min = x if self.min is None else min(self.min, x)
        self.max = x if self.max is None else max(self.max, x)

    def as_dict(self):
        if self.n > 1:
            variance = self.m2 / (self.n - 1)
            std = math.sqrt(variance)
        else:
            std = 0.0
        return {
            "count": self.n,
            "mean": self.mean,
            "std": std,
            "min": self.min,
            "max": self.max,
        }


def is_float_value(v):
    if v is None or v == "":
        return False
    try:
        float(v)
        return True
    except Exception:
        return False


def get_feature_values(row, features):
    vals = []
    for f in features:
        v = row.get(f, "")
        if not is_float_value(v):
            return None
        vals.append(float(v))
    return vals


def make_output_row(row, features):
    out = {k: row.get(k, "") for k in META}
    for f in features:
        out[f] = row.get(f, "")
    return out


with open(INPUT, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    input_fields = reader.fieldnames or []

features = [f for f in FEATURE_CANDIDATES if f in input_fields]
output_fields = META + features

stats = {f: Stats() for f in features}

counts = {
    "processed": 0,
    "normal_good_complete": 0,
    "train_written": 0,
    "val_written": 0,
    "normal_test_written": 0,
    "anomaly_test_written": 0,
    "data_quality_test_written": 0,
    "skipped_incomplete_numeric": 0,
}

with open(TRAIN, "w", newline="", encoding="utf-8") as f_train, \
     open(VAL, "w", newline="", encoding="utf-8") as f_val, \
     open(NORMAL_TEST, "w", newline="", encoding="utf-8") as f_ntest, \
     open(ANOMALY_TEST, "w", newline="", encoding="utf-8") as f_atest, \
     open(DATA_QUALITY_TEST, "w", newline="", encoding="utf-8") as f_dq, \
     open(INPUT, newline="", encoding="utf-8") as f_in:

    writers = {
        "train": csv.DictWriter(f_train, fieldnames=output_fields),
        "val": csv.DictWriter(f_val, fieldnames=output_fields),
        "normal_test": csv.DictWriter(f_ntest, fieldnames=output_fields),
        "anomaly_test": csv.DictWriter(f_atest, fieldnames=output_fields),
        "data_quality": csv.DictWriter(f_dq, fieldnames=output_fields),
    }

    for w in writers.values():
        w.writeheader()

    reader = csv.DictReader(f_in)

    for row in reader:
        counts["processed"] += 1

        state = row.get("health_state", "")
        quality = row.get("quality", "")

        vals = get_feature_values(row, features)

        if vals is None:
            if quality == "good":
                counts["skipped_incomplete_numeric"] += 1
            if quality != "good" and counts["data_quality_test_written"] < MAX_DATA_QUALITY_TEST:
                writers["data_quality"].writerow(make_output_row(row, features))
                counts["data_quality_test_written"] += 1
            continue

        if quality != "good":
            if counts["data_quality_test_written"] < MAX_DATA_QUALITY_TEST:
                writers["data_quality"].writerow(make_output_row(row, features))
                counts["data_quality_test_written"] += 1
            continue

        if state == "normal":
            counts["normal_good_complete"] += 1
            n = counts["normal_good_complete"]

            # deterministic downsampling across the full 10-day time range
            if n % 5 == 0 and counts["train_written"] < MAX_TRAIN:
                out = make_output_row(row, features)
                writers["train"].writerow(out)
                counts["train_written"] += 1
                for f_name, x in zip(features, vals):
                    stats[f_name].add(x)

            elif n % 17 == 0 and counts["val_written"] < MAX_VAL:
                writers["val"].writerow(make_output_row(row, features))
                counts["val_written"] += 1

            elif n % 31 == 0 and counts["normal_test_written"] < MAX_NORMAL_TEST:
                writers["normal_test"].writerow(make_output_row(row, features))
                counts["normal_test_written"] += 1

        elif state in ("warning", "abnormal"):
            if counts["anomaly_test_written"] < MAX_ANOMALY_TEST:
                writers["anomaly_test"].writerow(make_output_row(row, features))
                counts["anomaly_test_written"] += 1

        if counts["processed"] % 200000 == 0:
            print("PROCESSED_ROWS =", counts["processed"], "COUNTS =", counts, flush=True)

feature_payload = {
    "version": "v0_3",
    "source": INPUT,
    "features": features,
    "metadata_columns": META,
    "notes": [
        "Training set contains only quality=good and health_state=normal samples.",
        "Warning/abnormal samples are held out for testing.",
        "Scaler statistics are computed only from the training set.",
    ],
}

scaler_payload = {
    "version": "v0_3",
    "source": str(TRAIN),
    "method": "standard_scaler",
    "features": {f: stats[f].as_dict() for f in features},
}

summary_payload = {
    "input": INPUT,
    "outdir": str(OUTDIR),
    "files": {
        "train": str(TRAIN),
        "validation": str(VAL),
        "normal_test": str(NORMAL_TEST),
        "warning_abnormal_test": str(ANOMALY_TEST),
        "data_quality_test": str(DATA_QUALITY_TEST),
        "feature_list": str(FEATURE_LIST),
        "scaler_config": str(SCALER),
    },
    "feature_count": len(features),
    "features": features,
    "counts": counts,
}

FEATURE_LIST.write_text(json.dumps(feature_payload, indent=2), encoding="utf-8")
SCALER.write_text(json.dumps(scaler_payload, indent=2), encoding="utf-8")
SUMMARY.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
LOG.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

print("===== PHASE 5 ML DATASET PREPARATION COMPLETE =====")
print(json.dumps(summary_payload, indent=2))
