import argparse
import csv
from pathlib import Path

def to_float(row, key):
    try:
        v = row.get(key, "")
        if v == "" or v is None:
            return None
        return float(v)
    except Exception:
        return None

def severity(value, warn, critical):
    if value is None:
        return 0.0
    if value <= warn:
        return 0.0
    if value >= critical:
        return 1.0
    return (value - warn) / (critical - warn)

def score_row(row):
    parts = []
    reasons = []

    quality = row.get("quality", "")

    voltage_imb = to_float(row, "pcs_phase_voltage_imbalance")
    current_imb = to_float(row, "pcs_phase_current_imbalance")
    soc_delta = to_float(row, "pcs_soc_vs_bms_soc_delta")
    temp_spread = to_float(row, "bms_temperature_spread")
    cell_spread = to_float(row, "bms_cell_voltage_spread")
    dc_voltage_delta = to_float(row, "pcs_dc_voltage_vs_bms_voltage_delta")
    dc_current_delta = to_float(row, "pcs_dc_current_vs_bms_current_delta")
    bms_faults = to_float(row, "bms_fault_flag_count") or 0.0
    pcs_faults = to_float(row, "pcs_fault_flag_count") or 0.0

    if quality != "good":
        parts.append(("data_quality_issue", 1.0, 1.5))
        reasons.append("Telemetry quality is not good")

    s = severity(voltage_imb, warn=5.0, critical=30.0)
    parts.append(("pcs_phase_voltage_imbalance", s, 1.2))
    if s > 0:
        reasons.append(f"PCS phase voltage imbalance high: {voltage_imb}")

    s = severity(current_imb, warn=8.0, critical=35.0)
    parts.append(("pcs_phase_current_imbalance", s, 1.2))
    if s > 0:
        reasons.append(f"PCS phase current imbalance high: {current_imb}")

    s = severity(soc_delta, warn=1.0, critical=5.0)
    parts.append(("pcs_bms_soc_mismatch", s, 0.8))
    if s > 0:
        reasons.append(f"PCS and BMS SOC mismatch: {soc_delta}")

    s = severity(temp_spread, warn=4.0, critical=8.0)
    parts.append(("bms_temperature_spread", s, 1.0))
    if s > 0:
        reasons.append(f"BMS temperature spread high: {temp_spread}")

    s = severity(cell_spread, warn=8.0, critical=15.0)
    parts.append(("bms_cell_voltage_spread", s, 1.2))
    if s > 0:
        reasons.append(f"BMS cell voltage spread high: {cell_spread}")

    s = severity(dc_voltage_delta, warn=5.0, critical=10.0)
    parts.append(("pcs_bms_dc_voltage_delta", s, 1.0))
    if s > 0:
        reasons.append(f"PCS DC voltage and BMS voltage mismatch: {dc_voltage_delta}")

    s = severity(dc_current_delta, warn=20.0, critical=60.0)
    parts.append(("pcs_bms_dc_current_delta", s, 1.2))
    if s > 0:
        reasons.append(f"PCS DC current and BMS current mismatch: {dc_current_delta}")

    if bms_faults > 0:
        parts.append(("bms_fault_flags", 1.0, 2.0))
        reasons.append(f"BMS fault or alarm flags active: {bms_faults}")
    else:
        parts.append(("bms_fault_flags", 0.0, 2.0))

    if pcs_faults > 0:
        parts.append(("pcs_fault_flags", 1.0, 2.0))
        reasons.append(f"PCS fault or alarm flags active: {pcs_faults}")
    else:
        parts.append(("pcs_fault_flags", 0.0, 2.0))

    weighted_sum = sum(s * w for _, s, w in parts)
    weight_total = sum(w for _, _, w in parts)
    weighted_score = weighted_sum / weight_total if weight_total else 0.0
    max_score = max((s for _, s, _ in parts), default=0.0)

    anomaly_score = (0.6 * max_score) + (0.4 * weighted_score)

    if anomaly_score >= 0.70:
        state = "abnormal"
    elif anomaly_score >= 0.35:
        state = "warning"
    else:
        state = "normal"

    top_parts = sorted(parts, key=lambda x: x[1], reverse=True)[:3]
    top_keys = [name for name, score, _ in top_parts if score > 0]

    if reasons:
        reason_text = "; ".join(reasons[:5])
    elif top_keys:
        reason_text = "top_features=" + ",".join(top_keys)
    else:
        reason_text = "normal operating range"

    return round(anomaly_score, 4), state, reason_text

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    inp = Path(args.input)
    outp = Path(args.output)
    outp.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    state_counts = {}

    with inp.open(newline="", encoding="utf-8") as fin, outp.open("w", newline="", encoding="utf-8") as fout:
        reader = csv.DictReader(fin)
        fieldnames = list(reader.fieldnames) + [
            "anomaly_score",
            "health_state",
            "anomaly_reason",
        ]

        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            score, state, reason = score_row(row)
            row["anomaly_score"] = score
            row["health_state"] = state
            row["anomaly_reason"] = reason
            writer.writerow(row)

            total += 1
            state_counts[state] = state_counts.get(state, 0) + 1

            if total % 100000 == 0:
                print("PROCESSED_ROWS =", total, flush=True)

    print("INPUT =", str(inp), flush=True)
    print("OUTPUT =", str(outp), flush=True)
    print("TOTAL_ROWS =", total, flush=True)
    print("STATE_COUNTS =", state_counts, flush=True)
    print("DONE", flush=True)

if __name__ == "__main__":
    main()
