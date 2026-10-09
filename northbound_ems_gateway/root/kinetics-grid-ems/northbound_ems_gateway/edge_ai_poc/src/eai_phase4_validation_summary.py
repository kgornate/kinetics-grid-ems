#!/usr/bin/env python3

import csv
from collections import Counter

p = "/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/data/bess_anomaly_scored_v0_3_full_10d.csv"

state_counts = Counter()
source_state_counts = Counter()
bess_state_counts = Counter()
reason_counts = Counter()
source_reason_counts = Counter()

top_abnormal = []
top_warning = []

with open(p, newline="", encoding="utf-8") as f:
    r = csv.DictReader(f)

    for row in r:
        state = row.get("health_state", "")
        source = row.get("source_id", "")
        bess = row.get("bess_id", "")
        reason = row.get("anomaly_reason", "")
        score = float(row.get("anomaly_score", "0") or 0)

        state_counts[state] += 1
        source_state_counts[(source, state)] += 1
        bess_state_counts[(bess, state)] += 1

        if state in ("warning", "abnormal"):
            reason_counts[reason] += 1
            source_reason_counts[(source, reason)] += 1

        item = {
            "timestamp_utc": row.get("timestamp_utc", ""),
            "source_id": source,
            "bess_id": bess,
            "quality": row.get("quality", ""),
            "score": score,
            "state": state,
            "reason": reason,
            "pcs_phase_voltage_imbalance": row.get("pcs_phase_voltage_imbalance", ""),
            "pcs_phase_current_imbalance": row.get("pcs_phase_current_imbalance", ""),
            "pcs_dc_voltage_vs_bms_voltage_delta": row.get("pcs_dc_voltage_vs_bms_voltage_delta", ""),
            "pcs_dc_current_vs_bms_current_delta": row.get("pcs_dc_current_vs_bms_current_delta", ""),
            "bms_temperature_spread": row.get("bms_temperature_spread", ""),
            "bms_cell_voltage_spread": row.get("bms_cell_voltage_spread", ""),
            "pcs_fault_flag_count": row.get("pcs_fault_flag_count", ""),
            "bms_fault_flag_count": row.get("bms_fault_flag_count", ""),
            "pcs_total_active_power": row.get("pcs_total_active_power", ""),
            "pcs_soc": row.get("pcs_soc", ""),
            "bms_display_soc": row.get("bms_display_soc", ""),
        }

        if state == "abnormal":
            top_abnormal.append(item)
        elif state == "warning" and len(top_warning) < 50:
            top_warning.append(item)

print("===== PHASE 4 VALIDATION SUMMARY =====")
print()

print("STATE_COUNTS")
for k, v in state_counts.most_common():
    print(k, v)

print()
print("SOURCE_STATE_COUNTS")
for (source, state), count in sorted(source_state_counts.items()):
    print(source, state, count)

print()
print("BESS_STATE_COUNTS")
for (bess, state), count in sorted(bess_state_counts.items()):
    print(bess, state, count)

print()
print("TOP_20_ANOMALY_REASONS")
for reason, count in reason_counts.most_common(20):
    print(count, "|", reason)

print()
print("ABNORMAL_EVENTS")
for x in sorted(top_abnormal, key=lambda d: d["score"], reverse=True):
    print(x)

print()
print("WARNING_SAMPLE_FIRST_50")
for x in top_warning[:50]:
    print(x)
