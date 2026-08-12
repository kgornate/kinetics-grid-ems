#!/bin/sh
set -e
DB="/mnt/ems-logs/northbound_ems_gateway/nb_ems_gateway.db"
python3 - <<'PY'
import sqlite3, time, os, json
DB = "/mnt/ems-logs/northbound_ems_gateway/nb_ems_gateway.db"

def read_count():
    conn=sqlite3.connect(DB, timeout=20)
    conn.execute('PRAGMA busy_timeout=20000')
    cur=conn.cursor()
    count=cur.execute('SELECT COUNT(*) FROM fast_bess_samples').fetchone()[0]
    latest=cur.execute('''
        SELECT id,timestamp_utc,source_id,bess_id,schema_version,write_mode,profile_name,selected_signal_count,good_signal_count,bad_signal_count,quality
        FROM fast_bess_samples
        ORDER BY id DESC
        LIMIT 8
    ''').fetchall()
    conn.close()
    return count, latest

print('DB exists:', os.path.exists(DB))
if os.path.exists(DB):
    print('DB size MB:', round(os.path.getsize(DB)/(1024*1024), 2))

c1, latest1 = read_count()
print('Start count:', c1)
print('Latest at start:')
for r in latest1:
    print(r)

time.sleep(60)

c2, latest2 = read_count()
print('\nEnd count:', c2)
print('Rows added in 60 sec:', c2-c1)
print('Expected for 1-sec logger with 2 BESS: around 120 rows')
print('Latest at end:')
for r in latest2:
    print(r)
PY
