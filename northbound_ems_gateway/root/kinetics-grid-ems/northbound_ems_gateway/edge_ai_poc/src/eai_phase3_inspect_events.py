import csv
import heapq
from collections import Counter

INPUT = "/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/data/bess_anomaly_scored_v0_3_full_10d.csv"

TOP_EVENTS_CSV = "/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/data/bess_anomaly_top_events_v0_3_full_10d.csv"
ABNORMAL_ONLY_CSV = "/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/data/bess_anomaly_abnormal_only_v0_3_full_10d.csv"
WARNING_SAMPLE_CSV = "/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/data/bess_anomaly_warning_sample_v0_3_full_10d.csv"
SUMMARY_TXT = "/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/logs/eai_phase3_event_inspection_summary.txt"

KEEP_FIELDS = [
    "timestamp_utc",
    "source_id",
    "bess_id",
    "quality",
    "anomaly_score",
    "health_state",
    "anomaly_reason",

    "pcs_phase_voltage_imbalance",
    "pcs_phase_current_imbalance",
    "pcs_dc_voltage_vs_bms_voltage_delta",
    "pcs_dc_current_vs_bms_current_delta",
    "pcs_soc_vs_bms_soc_delta",

    "bms_temperature_spread",
    "bms_cell_voltage_spread",

    "pcs_fault_flag_count",
    "bms_fault_flag_count",

    "pcs_phase_a_voltage",
    "pcs_phase_b_voltage",
    "pcs_phase_c_voltage",
    "pcs_phase_a_current",
    "pcs_phase_b_current",
    "pcs_phase_c_current",

    "pcs_dc_voltage",
    "pcs_dc_current",
    "pcs_total_active_power",
    "pcs_soc",

    "bms_cluster_total_voltage",
    "bms_cluster_total_current",
    "bms_display_soc",
    "bms_soh",
]

def to_float(row, key):
    try:
        v = row.get(key, "")
        if v == "" or v is None:
            return 0.0
        return float(v)
    except Exception:
        return 0.0

def compact(row):
    return {k: row.get(k, "") for k in KEEP_FIELDS}

def main():
    state_counts = Counter()
    source_counts = Counter()
    source_state_counts = Counter()
    quality_counts = Counter()
    quality_state_counts = Counter()
    reason_counts = Counter()

    top_heap = []
    abnormal_rows = []
    warning_sample = []

    seq = 0

    with open(INPUT, newline="", encoding="utf-8") as fin:
        reader = csv.DictReader(fin)

        for row in reader:
            seq += 1

            state = row.get("health_state", "")
            source = row.get("source_id", "")
            quality = row.get("quality", "")
            reason = row.get("anomaly_reason", "")

            state_counts[state] += 1
            source_counts[source] += 1
            source_state_counts[(source, state)] += 1
            quality_counts[quality] += 1
            quality_state_counts[(quality, state)] += 1

            if state in ("warning", "abnormal"):
                reason_counts[reason] += 1

            score = to_float(row, "anomaly_score")
            item = compact(row)

            if state == "abnormal":
                abnormal_rows.append(item)

            if state == "warning" and len(warning_sample) < 200:
                warning_sample.append(item)

            if len(top_heap) < 200:
                heapq.heappush(top_heap, (score, seq, item))
            else:
                heapq.heappushpop(top_heap, (score, seq, item))

            if seq % 200000 == 0:
                print("PROCESSED_ROWS =", seq, flush=True)

    top_rows = [
        item for score, seq, item in
        sorted(top_heap, key=lambda x: x[0], reverse=True)
    ]

    with open(TOP_EVENTS_CSV, "w", newline="", encoding="utf-8") as fout:
        writer = csv.DictWriter(fout, fieldnames=KEEP_FIELDS)
        writer.writeheader()
        writer.writerows(top_rows)

    with open(ABNORMAL_ONLY_CSV, "w", newline="", encoding="utf-8") as fout:
        writer = csv.DictWriter(fout, fieldnames=KEEP_FIELDS)
        writer.writeheader()
        writer.writerows(abnormal_rows)

    with open(WARNING_SAMPLE_CSV, "w", newline="", encoding="utf-8") as fout:
        writer = csv.DictWriter(fout, fieldnames=KEEP_FIELDS)
        writer.writeheader()
        writer.writerows(warning_sample)

    with open(SUMMARY_TXT, "w", encoding="utf-8") as s:
        def w(line=""):
            print(line)
            s.write(str(line) + "\n")

        w("===== PHASE 3 EVENT INSPECTION SUMMARY =====")
        w("INPUT = " + INPUT)
        w("TOTAL_ROWS = " + str(seq))
        w("")

        w("STATE_COUNTS")
        for k, v in state_counts.most_common():
            w(f"{k}: {v}")

        w("")
        w("SOURCE_COUNTS")
        for k, v in source_counts.most_common():
            w(f"{k}: {v}")

        w("")
        w("SOURCE_STATE_COUNTS")
        for (source, state), v in sorted(source_state_counts.items()):
            w(f"{source} | {state}: {v}")

        w("")
        w("QUALITY_COUNTS")
        for k, v in quality_counts.most_common():
            w(f"{k}: {v}")

        w("")
        w("QUALITY_STATE_COUNTS")
        for (quality, state), v in sorted(quality_state_counts.items()):
            w(f"{quality} | {state}: {v}")

        w("")
        w("TOP_REASONS")
        for reason, count in reason_counts.most_common(30):
            w(f"{count}: {reason}")

        w("")
        w("ABNORMAL_ROWS")
        for r in abnormal_rows:
            w(str(r))

        w("")
        w("TOP_20_EVENTS_BY_SCORE")
        for r in top_rows[:20]:
            w(str(r))

        w("")
        w("OUTPUT_TOP_EVENTS_CSV = " + TOP_EVENTS_CSV)
        w("OUTPUT_ABNORMAL_ONLY_CSV = " + ABNORMAL_ONLY_CSV)
        w("OUTPUT_WARNING_SAMPLE_CSV = " + WARNING_SAMPLE_CSV)
        w("DONE")

if __name__ == "__main__":
    main()
