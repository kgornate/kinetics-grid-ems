#!/usr/bin/env python3

import csv
from datetime import datetime, timezone
from collections import Counter

INPUT = "/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/data/bess_anomaly_scored_v0_3_full_10d.csv"
OUTPUT = "/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/data/bess_anomaly_event_windows_v0_3_full_10d.csv"
SUMMARY = "/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/logs/eai_phase4_1_event_windows_summary.log"

GAP_SEC = 30


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def reason_categories(reason):
    cats = []
    r = reason.lower()

    if "telemetry quality" in r:
        cats.append("data_quality")
    if "pcs fault" in r or "alarm flags" in r:
        cats.append("pcs_fault_or_alarm")
    if "phase voltage imbalance" in r:
        cats.append("pcs_phase_voltage_imbalance")
    if "phase current imbalance" in r:
        cats.append("pcs_phase_current_imbalance")
    if "dc current and bms current mismatch" in r:
        cats.append("pcs_bms_current_mismatch")
    if "dc voltage and bms voltage mismatch" in r:
        cats.append("pcs_bms_voltage_mismatch")
    if "cell voltage spread" in r:
        cats.append("bms_cell_voltage_spread")
    if "temperature spread" in r:
        cats.append("bms_temperature_spread")
    if "soc" in r:
        cats.append("soc_mismatch")

    return cats or ["other"]


def severity_rank(state):
    return {"normal": 0, "warning": 1, "abnormal": 2}.get(state, 0)


def new_event(row, ts):
    cats = reason_categories(row.get("anomaly_reason", ""))
    return {
        "source_id": row.get("source_id", ""),
        "bess_id": row.get("bess_id", ""),
        "start_ts": ts,
        "end_ts": ts,
        "row_count": 1,
        "dominant_state": row.get("health_state", ""),
        "max_score": float(row.get("anomaly_score", "0") or 0),
        "categories": Counter(cats),
        "reasons": Counter([row.get("anomaly_reason", "")]),
        "max_pcs_phase_voltage_imbalance": float(row.get("pcs_phase_voltage_imbalance", "0") or 0),
        "max_pcs_phase_current_imbalance": float(row.get("pcs_phase_current_imbalance", "0") or 0),
        "max_pcs_dc_current_vs_bms_current_delta": float(row.get("pcs_dc_current_vs_bms_current_delta", "0") or 0),
        "max_pcs_dc_voltage_vs_bms_voltage_delta": float(row.get("pcs_dc_voltage_vs_bms_voltage_delta", "0") or 0),
        "max_bms_cell_voltage_spread": float(row.get("bms_cell_voltage_spread", "0") or 0),
        "max_bms_temperature_spread": float(row.get("bms_temperature_spread", "0") or 0),
        "max_pcs_fault_flag_count": float(row.get("pcs_fault_flag_count", "0") or 0),
        "max_bms_fault_flag_count": float(row.get("bms_fault_flag_count", "0") or 0),
    }


def update_event(ev, row, ts):
    ev["end_ts"] = ts
    ev["row_count"] += 1

    state = row.get("health_state", "")
    if severity_rank(state) > severity_rank(ev["dominant_state"]):
        ev["dominant_state"] = state

    score = float(row.get("anomaly_score", "0") or 0)
    ev["max_score"] = max(ev["max_score"], score)

    for c in reason_categories(row.get("anomaly_reason", "")):
        ev["categories"][c] += 1

    ev["reasons"][row.get("anomaly_reason", "")] += 1

    def max_field(name, col):
        try:
            ev[name] = max(ev[name], float(row.get(col, "0") or 0))
        except Exception:
            pass

    max_field("max_pcs_phase_voltage_imbalance", "pcs_phase_voltage_imbalance")
    max_field("max_pcs_phase_current_imbalance", "pcs_phase_current_imbalance")
    max_field("max_pcs_dc_current_vs_bms_current_delta", "pcs_dc_current_vs_bms_current_delta")
    max_field("max_pcs_dc_voltage_vs_bms_voltage_delta", "pcs_dc_voltage_vs_bms_voltage_delta")
    max_field("max_bms_cell_voltage_spread", "bms_cell_voltage_spread")
    max_field("max_bms_temperature_spread", "bms_temperature_spread")
    max_field("max_pcs_fault_flag_count", "pcs_fault_flag_count")
    max_field("max_bms_fault_flag_count", "bms_fault_flag_count")


def flush_event(ev, out_rows, event_id):
    duration_sec = max(0.0, (ev["end_ts"] - ev["start_ts"]).total_seconds())

    top_categories = ";".join([k for k, _ in ev["categories"].most_common(5)])
    top_reason = ev["reasons"].most_common(1)[0][0]

    out_rows.append({
        "event_id": event_id,
        "source_id": ev["source_id"],
        "bess_id": ev["bess_id"],
        "dominant_state": ev["dominant_state"],
        "start_utc": ev["start_ts"].isoformat(),
        "end_utc": ev["end_ts"].isoformat(),
        "duration_sec": round(duration_sec, 3),
        "row_count": ev["row_count"],
        "max_score": round(ev["max_score"], 4),
        "top_categories": top_categories,
        "top_reason": top_reason,
        "max_pcs_phase_voltage_imbalance": ev["max_pcs_phase_voltage_imbalance"],
        "max_pcs_phase_current_imbalance": ev["max_pcs_phase_current_imbalance"],
        "max_pcs_dc_current_vs_bms_current_delta": ev["max_pcs_dc_current_vs_bms_current_delta"],
        "max_pcs_dc_voltage_vs_bms_voltage_delta": ev["max_pcs_dc_voltage_vs_bms_voltage_delta"],
        "max_bms_cell_voltage_spread": ev["max_bms_cell_voltage_spread"],
        "max_bms_temperature_spread": ev["max_bms_temperature_spread"],
        "max_pcs_fault_flag_count": ev["max_pcs_fault_flag_count"],
        "max_bms_fault_flag_count": ev["max_bms_fault_flag_count"],
    })


active = {}
events = []
event_id = 0
processed = 0
anomaly_rows = 0

with open(INPUT, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)

    for row in reader:
        processed += 1
        state = row.get("health_state", "")

        if state == "normal":
            continue

        anomaly_rows += 1
        ts = parse_ts(row["timestamp_utc"])
        key = (row.get("source_id", ""), row.get("bess_id", ""))

        if key not in active:
            active[key] = new_event(row, ts)
            continue

        ev = active[key]
        gap = (ts - ev["end_ts"]).total_seconds()

        if gap <= GAP_SEC:
            update_event(ev, row, ts)
        else:
            event_id += 1
            flush_event(ev, events, event_id)
            active[key] = new_event(row, ts)

for ev in active.values():
    event_id += 1
    flush_event(ev, events, event_id)

fields = [
    "event_id", "source_id", "bess_id", "dominant_state",
    "start_utc", "end_utc", "duration_sec", "row_count",
    "max_score", "top_categories", "top_reason",
    "max_pcs_phase_voltage_imbalance",
    "max_pcs_phase_current_imbalance",
    "max_pcs_dc_current_vs_bms_current_delta",
    "max_pcs_dc_voltage_vs_bms_voltage_delta",
    "max_bms_cell_voltage_spread",
    "max_bms_temperature_spread",
    "max_pcs_fault_flag_count",
    "max_bms_fault_flag_count",
]

with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(events)

state_counts = Counter(e["dominant_state"] for e in events)
source_counts = Counter((e["source_id"], e["dominant_state"]) for e in events)
category_counts = Counter()
for e in events:
    for c in e["top_categories"].split(";"):
        if c:
            category_counts[c] += 1

lines = []
lines.append("===== PHASE 4.1 EVENT WINDOW SUMMARY =====")
lines.append(f"INPUT = {INPUT}")
lines.append(f"OUTPUT = {OUTPUT}")
lines.append(f"PROCESSED_ROWS = {processed}")
lines.append(f"WARNING_ABNORMAL_ROWS = {anomaly_rows}")
lines.append(f"EVENT_WINDOWS = {len(events)}")
lines.append(f"GAP_SEC = {GAP_SEC}")
lines.append("")
lines.append("EVENT_STATE_COUNTS")
for k, v in state_counts.most_common():
    lines.append(f"{k} {v}")
lines.append("")
lines.append("EVENT_SOURCE_COUNTS")
for (source, state), count in sorted(source_counts.items()):
    lines.append(f"{source} {state} {count}")
lines.append("")
lines.append("EVENT_CATEGORY_COUNTS")
for k, v in category_counts.most_common():
    lines.append(f"{k} {v}")
lines.append("")
lines.append("TOP_20_EVENTS_BY_SCORE")
for e in sorted(events, key=lambda x: float(x["max_score"]), reverse=True)[:20]:
    lines.append(str(e))

text = "\n".join(lines)
print(text)

with open(SUMMARY, "w", encoding="utf-8") as f:
    f.write(text + "\n")
