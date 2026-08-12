#!/bin/sh
set -e
DB="/mnt/ems-logs/northbound_ems_gateway/nb_ems_gateway.db"
python3 - <<'PY'
import os, sqlite3, time
DB = "/mnt/ems-logs/northbound_ems_gateway/nb_ems_gateway.db"
print("DB exists:", os.path.exists(DB))
if os.path.exists(DB):
    print("DB size MB:", round(os.path.getsize(DB)/(1024*1024), 2))
conn = sqlite3.connect(DB, timeout=10)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA busy_timeout=10000")
cur = conn.cursor()
for table in ["telemetry_snapshots", "telemetry_points", "gateway_events", "fast_bess_samples"]:
    try:
        print(table, cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except Exception as exc:
        print(table, "ERROR", exc)
print("\nfast_bess_samples schema columns:")
try:
    print([r[1] for r in cur.execute("PRAGMA table_info(fast_bess_samples)").fetchall()])
except Exception as exc:
    print("ERROR", exc)
print("\nLatest fast BESS samples:")
try:
    for row in cur.execute("""
        SELECT id, timestamp_utc, source_id, bess_id, schema_version, write_mode, profile_name,
               selected_signal_count, good_signal_count, bad_signal_count, quality
        FROM fast_bess_samples
        ORDER BY timestamp_epoch_ms DESC
        LIMIT 10
    """):
        print(tuple(row))
except Exception as exc:
    print("ERROR", exc)
conn.close()
PY
