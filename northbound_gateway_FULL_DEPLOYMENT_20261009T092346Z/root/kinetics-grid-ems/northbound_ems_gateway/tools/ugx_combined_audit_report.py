from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create a UGX uploader audit report from journalctl raw logs")
    p.add_argument("--raw-log", required=True, help="Path to journalctl raw log file")
    p.add_argument("--output", required=True, help="Output markdown report path")
    p.add_argument("--cloud-url", default="https://platform.uniqgrid.com/api/v1/EMSTEST/telemetry")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    log_path = Path(args.raw_log)
    out_path = Path(args.output)
    cloud_url = args.cloud_url
    text = log_path.read_text(errors="ignore")
    lines = text.splitlines()

    cloud_post_ok = 0
    cloud_post_fail = 0
    local_login_post = 0
    local_gets = Counter()
    combined_cycles = 0
    combined_records = 0
    combined_payload_bytes = 0
    combined_fast_records = 0
    combined_frequency_records = 0
    combined_not_due = 0
    separated_fast_cycles = 0
    separated_fast_records = 0
    separated_freq_cycles = Counter()
    separated_freq_records = Counter()
    separated_freq_values = Counter()

    for line in lines:
        if f'POST {cloud_url} "HTTP/1.1 200 OK"' in line:
            cloud_post_ok += 1
        if "UGX POST exception" in line or "WriteTimeout" in line or "ReadTimeout" in line:
            cloud_post_fail += 1
        if 'POST http://127.0.0.1:8000/api/auth/login "HTTP/1.1 200 OK"' in line:
            local_login_post += 1
        m = re.search(r'GET (http://127\.0\.0\.1:8000/api/assets/[^ ]+) "HTTP/1\.1 200 OK"', line)
        if m:
            local_gets[m.group(1)] += 1
        if "cycle result:" not in line:
            continue
        raw = line.split("cycle result:", 1)[1].strip()
        try:
            data = json.loads(raw)
        except Exception:
            continue

        if "ugx_combined" in data:
            uc = data.get("ugx_combined") or {}
            if uc.get("reason") == "combined_not_due":
                combined_not_due += 1
            cp = uc.get("combined_post") or {}
            if cp.get("ok") is True and cp.get("single_cloud_post") is True:
                combined_cycles += 1
                combined_records += int(cp.get("uploaded_records") or 0)
                combined_payload_bytes += int(cp.get("payload_bytes") or 0)
                fb = uc.get("fast_bess") or {}
                combined_fast_records += int(fb.get("pending_records") or 0)
                uf = uc.get("ugx_frequency") or {}
                profiles = uf.get("profiles") or {}
                combined_frequency_records += len([p for p in profiles.values() if isinstance(p, dict) and p.get("pending_records")])
            continue

        fb = data.get("fast_bess", {})
        if fb.get("ok") is True and "uploaded_records" in fb:
            separated_fast_cycles += 1
            separated_fast_records += int(fb.get("uploaded_records") or 0)
        uf = data.get("ugx_frequency", {})
        for freq, profile in (uf.get("profiles") or {}).items():
            if isinstance(profile, dict) and profile.get("ok") is True:
                separated_freq_cycles[str(freq)] += 1
                separated_freq_records[str(freq)] += int(profile.get("uploaded_records") or 0)
                separated_freq_values[str(freq)] += int(profile.get("value_count") or 0)

    report = []
    report.append("# UGX Telemetry Upload Audit Report")
    report.append("")
    report.append("## Summary")
    report.append("")
    report.append(f"- External UGX telemetry endpoint used: `{cloud_url}`")
    report.append(f"- Successful cloud POST requests to UGX: `{cloud_post_ok}`")
    report.append(f"- Failed cloud POST attempts/timeouts detected: `{cloud_post_fail}`")
    report.append(f"- Internal localhost login POST calls: `{local_login_post}`")
    report.append(f"- Internal localhost telemetry GET calls: `{sum(local_gets.values())}`")
    report.append("")
    report.append("## U1.3 combined-post breakdown")
    report.append("")
    report.append(f"- Combined cloud POST cycles: `{combined_cycles}`")
    report.append(f"- Combined uploaded timestamped records: `{combined_records}`")
    report.append(f"- Combined fast BESS records included: `{combined_fast_records}`")
    report.append(f"- Combined frequency records included: `{combined_frequency_records}`")
    report.append(f"- Combined payload bytes total: `{combined_payload_bytes}`")
    report.append(f"- Combined not-due checks: `{combined_not_due}`")
    report.append("")
    report.append("## Legacy separated-post breakdown, if present")
    report.append("")
    report.append(f"- Separated fast cycles: `{separated_fast_cycles}`")
    report.append(f"- Separated fast timestamped records: `{separated_fast_records}`")
    for freq in sorted(separated_freq_cycles, key=lambda x: int(x)):
        report.append(f"- Separated `{freq}` second profile cycles: `{separated_freq_cycles[freq]}`, records: `{separated_freq_records[freq]}`, total values: `{separated_freq_values[freq]}`")
    report.append("")
    report.append("## Important clarification")
    report.append("")
    report.append("The gateway uses one UGX cloud telemetry endpoint only. Localhost calls to `127.0.0.1:8000` are internal gateway reads and do not hit the UGX server.")
    report.append("")
    report.append("## Internal localhost APIs used")
    report.append("")
    report.append("- `POST http://127.0.0.1:8000/api/auth/login`")
    for url, count in sorted(local_gets.items()):
        report.append(f"- `{url}` -> `{count}` calls")
    report.append("")
    report.append("## Raw log file")
    report.append("")
    report.append(f"- `{log_path}`")
    out_path.write_text("\n".join(report))
    print(f"REPORT_CREATED: {out_path}")


if __name__ == "__main__":
    main()
