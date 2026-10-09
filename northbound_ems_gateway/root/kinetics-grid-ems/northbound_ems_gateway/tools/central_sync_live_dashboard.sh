#!/bin/sh
set -u

TARGET="${1:-/root/kinetics-grid-ems/northbound_ems_gateway}"
DB="/mnt/ems-logs/northbound_ems_gateway/central_sync_outbox.db"
STATUS="/var/lib/nb-ems-central-sync/status.json"
OVERFLOW="/var/lib/nb-ems-central-sync/overflow_archiver_status.json"
RECOVERY="/var/lib/nb-ems-central-sync/overflow_recovery_status.json"

cd "$TARGET" || exit 1

while true; do
    printf '\033[2J\033[H'
    echo "================================================================================"
    echo "             NORTHBOUND EMS - LIVE STREAM / BACKEND ACK DASHBOARD"
    echo "================================================================================"
    echo " Time UTC : $(date -u '+%Y-%m-%d %H:%M:%S')"
    echo

    LIVE="$(systemctl is-active central-sync.service 2>/dev/null || true)"
    REPLAY="$(systemctl is-active central-sync-backlog-replay.service 2>/dev/null || true)"
    printf " Central Sync   : %-10s    Legacy Replay  : %-10s\n" "$LIVE" "$REPLAY"
    python3 - "$STATUS" <<'PY'
import json,sys
try:
    d=json.load(open(sys.argv[1]))
    t=d.get("transport_control") or {}
    print(" Transport      : %s" % ("PAUSED (producers still logging)" if t.get("paused") else "RUNNING"))
except Exception:
    print(" Transport      : status unavailable")
PY

    PID="$(systemctl show central-sync.service -p MainPID --value 2>/dev/null || true)"
    if [ -n "$PID" ] && [ "$PID" != "0" ]; then
        ps -p "$PID" -o pid,%cpu,rss,etime --no-headers 2>/dev/null | awk '{printf " PID            : %-8s    CPU : %-6s%%    RAM : %.1f MB    Uptime : %s\n",$1,$2,$3/1024,$4}'
    fi
    free -m | awk '/^Mem:/ {printf " System RAM     : %s MB total | %s MB used | %s MB available\n",$2,$3,$7}'

    echo
    echo "---------------- PER-STREAM GENERATION + BACKEND ACK ---------------------------"
    python3 - "$DB" "$STATUS" "configs/central_sync.json" <<'PY'
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB, STATUS, CFG = sys.argv[1:]
now = datetime.now(timezone.utc)

stream_defs = [
    ("S1", "fast_bess_telemetry", "Fast BESS", "fast_bess", False),
    ("S2", "general_asset_telemetry", "General Assets", "general_assets", False),
    ("S3", "gateway_health", "Gateway Health", "gateway_health", False),
    ("S4", "alarms_events", "Alarms / Events", "alarms_events", True),
    ("S5", "soc_controller", "SOC Controller", "soc_controller", False),
    ("S6", "solis", "Solis", "solis", False),
    ("S7", "edge_ai", "Edge AI", "edge_ai", False),
    ("S8", "configuration_audit", "Config Audit", "configuration_audit", True),
]

def parse_ts(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None

def age(v):
    t = parse_ts(v)
    if not t:
        return None
    return max(0.0, (now - t).total_seconds())

def age_text(v):
    a = age(v)
    if a is None:
        return "--"
    if a < 1000:
        return f"{a:.1f}s"
    if a < 86400:
        return f"{a/3600:.1f}h"
    return f"{a/86400:.1f}d"

try:
    cfg = json.loads(Path(CFG).read_text())
except Exception:
    cfg = {}
try:
    status = json.loads(Path(STATUS).read_text())
except Exception:
    status = {}
acks = status.get("stream_backend_ack", {}) or {}
started = parse_ts(status.get("started_utc"))

seq = {}
queue = {}
try:
    con = sqlite3.connect(DB, timeout=2)
    con.row_factory = sqlite3.Row
    for row in con.execute("""
        SELECT stream, COUNT(*) AS subs, MAX(last_sequence) AS max_seq,
               MAX(updated_utc) AS last_utc
        FROM sequences GROUP BY stream
    """):
        seq[row["stream"]] = dict(row)
    for row in con.execute("""
        SELECT stream, COUNT(*) AS msgs,
               COALESCE(SUM(payload_bytes),0) AS bytes,
               MIN(created_at_utc) AS oldest_utc
        FROM outbox_messages
        WHERE state IN ('pending','retry','inflight')
        GROUP BY stream
    """):
        queue[row["stream"]] = dict(row)
    con.close()
except Exception as exc:
    print(" DB read error:", exc)

print(f" {'ID':<3} {'Stream':<18} {'Cfg':<4} {'GenAge':>8} {'AckAge':>8} {'ACKs':>7} {'Queue':>6} {'Last backend result':<20}")
print(f" {'--':<3} {'-'*18:<18} {'---':<4} {'-'*8:>8} {'-'*8:>8} {'-'*7:>7} {'-'*6:>6} {'-'*20:<20}")
for sid, stream, label, cfg_key, event_driven in stream_defs:
    enabled = bool(cfg.get(cfg_key, {}).get("enabled", False))
    s = seq.get(stream, {})
    a = acks.get(stream, {})
    q = queue.get(stream, {})
    ack_count = int(a.get("acked_count", 0) or 0)
    result = str(a.get("last_backend_result") or "--")
    if not enabled:
        result = "DISABLED"
    elif event_driven and ack_count == 0:
        last_gen = parse_ts(s.get("last_utc"))
        if started and (last_gen is None or last_gen < started):
            result = "EVENT-IDLE"
    print(
        f" {sid:<3} {label:<18} "
        f"{('ON' if enabled else 'OFF'):<4} "
        f"{age_text(s.get('last_utc')):>8} "
        f"{age_text(a.get('last_ack_utc')):>8} "
        f"{ack_count:>7} "
        f"{int(q.get('msgs',0) or 0):>6} "
        f"{result:<20}"
    )

print()
print(" ACK counters are backend-confirmed per-message ACKs since current Central Sync start.")
print(" accepted/already_processed = ACK success; EVENT-IDLE is normal for S4/S8 with no new event.")
PY

    echo
    echo "---------------- LAST 60 SEC BACKEND TRANSPORT --------------------------------"
    sqlite3 -header -column "$DB" '
    SELECT outcome,
           COALESCE(http_status,"-") AS http,
           COUNT(*) AS requests,
           SUM(message_count) AS messages,
           ROUND(SUM(payload_bytes)/1024.0/1024.0,2) AS mb
    FROM transport_attempts
    WHERE attempted_utc >= strftime("%Y-%m-%dT%H:%M:%SZ","now","-60 seconds")
    GROUP BY outcome,http_status
    ORDER BY outcome;
    ' 2>/dev/null || true

    echo
    echo "---------------- CURRENT LIVE OUTBOX ------------------------------------------"
    sqlite3 -header -column "$DB" '
    SELECT state,
           COUNT(*) AS messages,
           ROUND(COALESCE(SUM(payload_bytes),0)/1024.0/1024.0,3) AS mb,
           ROUND(COALESCE((julianday("now")-julianday(MIN(created_at_utc)))*86400.0,0),1) AS oldest_sec
    FROM outbox_messages
    WHERE state IN ("pending","retry","inflight")
    GROUP BY state
    ORDER BY state;
    ' 2>/dev/null || true

    echo
    echo "---------------- OVERFLOW -----------------------------------------------------"
    python3 - "$OVERFLOW" <<'PY'
import json, sys
from pathlib import Path
try:
    d=json.loads(Path(sys.argv[1]).read_text())
    c=d.get("counters",{})
    print(" Running=%s  Archived=%s  Payload=%.2f MB  SpillCycles=%s  Failures=%s" % (
        d.get("running"), c.get("archived_message_count",0),
        c.get("archived_payload_bytes",0)/1024/1024,
        c.get("spill_cycle_count",0), c.get("failure_count",0)))
except Exception:
    print(" Overflow status unavailable")
PY

    echo
    echo "---------------- OVERFLOW RECOVERY --------------------------------------------"
    python3 - "$RECOVERY" <<'PY'
import json, sys
from pathlib import Path
try:
    d=json.loads(Path(sys.argv[1]).read_text())
    c=d.get("counters",{})
    gate=d.get("resource_gate",{}) or {}
    print(" Running=%s  Archive=%s  ReplayReq=%s  Drained=%s  Paused=%s  Failures=%s" % (
        d.get("running"), c.get("last_archive_path") or "--",
        c.get("request_cycle_count",0), c.get("archive_drained_count",0),
        c.get("last_pause_reason") or "--", c.get("failure_count",0)))
except Exception:
    print(" Overflow recovery status unavailable")
PY

    echo
    echo "================================================================================"
    echo " Healthy: S1-S8 ON | transport RUNNING or intentionally PAUSED | HTTP 200 when online"
    echo " Refresh every 5 sec                                            Ctrl+C to exit"
    echo "================================================================================"
    sleep 5
done
