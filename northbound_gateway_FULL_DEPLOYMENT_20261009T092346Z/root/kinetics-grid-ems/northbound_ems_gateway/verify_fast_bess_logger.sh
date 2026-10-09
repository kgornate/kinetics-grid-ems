#!/bin/sh
set -e
DB="/mnt/ems-logs/northbound_ems_gateway/nb_ems_gateway.db"
python3 - <<'PY'
import os, sqlite3
DB = "/mnt/ems-logs/northbound_ems_gateway/nb_ems_gateway.db"
print("DB exists:", os.path.exists(DB))
if os.path.exists(DB):
    print("DB size MB:", round(os.path.getsize(DB)/(1024*1024), 2))
conn = sqlite3.connect(DB)
cur = conn.cursor()
for table in ["telemetry_snapshots", "telemetry_points", "gateway_events", "fast_bess_samples"]:
    try:
        print(table, cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except Exception as exc:
        print(table, "ERROR", exc)
print("Latest fast BESS samples:")
try:
    for row in cur.execute("""
        SELECT timestamp_utc, source_id, bess_id, selected_signal_count, good_signal_count, bad_signal_count, quality
        FROM fast_bess_samples
        ORDER BY timestamp_epoch_ms DESC
        LIMIT 10
    """):
        print(row)
except Exception as exc:
    print("ERROR", exc)
conn.close()
PY
