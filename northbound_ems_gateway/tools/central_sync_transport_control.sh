#!/bin/sh
set -eu

PROJECT="${PROJECT:-/root/kinetics-grid-ems/northbound_ems_gateway}"
CFG="${CFG:-$PROJECT/configs/central_sync.json}"
STATUS="/var/lib/nb-ems-central-sync/status.json"
DB="/mnt/ems-logs/northbound_ems_gateway/central_sync_outbox.db"

PAUSE_FILE="$(python3 - "$CFG" <<'PY'
import json,sys
p=sys.argv[1]
d=json.load(open(p))
print((d.get('uploader') or {}).get('pause_file') or '/var/lib/nb-ems-central-sync/uploader.pause')
PY
)"

usage() {
    echo "Usage: $0 pause [reason] | resume | status"
}

show_status() {
    echo "Central Sync service : $(systemctl is-active central-sync.service 2>/dev/null || true)"
    echo "Legacy replay service: $(systemctl is-active central-sync-backlog-replay.service 2>/dev/null || true)"
    if [ -e "$PAUSE_FILE" ]; then
        echo "Transport            : PAUSED"
        echo "Pause file           : $PAUSE_FILE"
        cat "$PAUSE_FILE" 2>/dev/null || true
    else
        echo "Transport            : RUNNING"
        echo "Pause file           : $PAUSE_FILE (absent)"
    fi
    if [ -f "$STATUS" ]; then
        python3 - "$STATUS" <<'PY'
import json,sys
try:
    d=json.load(open(sys.argv[1]))
except Exception as e:
    print('Status JSON          : unavailable:',e)
    raise SystemExit(0)
t=(d.get('transport_control') or {})
u=(d.get('uploader') or {})
print('Uploader status       : paused=%s active_requests=%s requests=%s success=%s failures=%s' % (
    t.get('paused'),u.get('active_request_count'),u.get('request_count'),u.get('request_success_count'),u.get('request_failure_count')))
PY
    fi
    if [ -f "$DB" ]; then
        sqlite3 "$DB" "SELECT state,COUNT(*),ROUND(COALESCE(SUM(payload_bytes),0)/1024.0/1024.0,3) FROM outbox_messages WHERE state IN ('pending','retry','inflight') GROUP BY state ORDER BY state;" 2>/dev/null || true
    fi
}

case "${1:-}" in
    pause)
        reason="${2:-manual_operator_pause}"
        mkdir -p "$(dirname "$PAUSE_FILE")"
        tmp="${PAUSE_FILE}.tmp.$$"
        python3 - "$tmp" "$reason" <<'PY'
import json,sys
from datetime import datetime,timezone
p,reason=sys.argv[1:]
with open(p,'w',encoding='utf-8') as f:
    json.dump({
        'paused_utc': datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
        'reason': reason,
        'scope': 'backend_transport_only',
        'producers_continue': True,
    },f,indent=2)
    f.write('\n')
PY
        mv "$tmp" "$PAUSE_FILE"
        echo "TRANSPORT_PAUSE=REQUESTED"
        sleep 2
        show_status
        ;;
    resume)
        rm -f "$PAUSE_FILE"
        echo "TRANSPORT_RESUME=REQUESTED"
        sleep 2
        show_status
        ;;
    status)
        show_status
        ;;
    *)
        usage
        exit 2
        ;;
esac
