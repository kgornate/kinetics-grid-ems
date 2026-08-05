# Phase 1.5 FRDM Deployment, Validation and Rollback

Keep Flutter monitoring-only and `bess-seven-day-v302.service` disabled/inactive.

## Extract, back up and install

```bash
rm -rf /tmp/kinetics_phase1_5_patch
mkdir -p /tmp/kinetics_phase1_5_patch
tar -xzf /root/Kinetics_Gateway_Phase1_5_WebSocket_Backpressure_20260805.tar.gz -C /tmp/kinetics_phase1_5_patch

BACKEND=/opt/kinetics-gateway/backend
PATCH=/tmp/kinetics_phase1_5_patch
BACKUP="/root/kinetics_phase1_5_backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP/app/api" "$BACKUP/app/core" "$BACKUP/app/services" "$BACKUP/tests"
cp -a "$BACKEND/app/api/routes.py" "$BACKUP/app/api/"
cp -a "$BACKEND/app/core/config.py" "$BACKUP/app/core/"
cp -a "$BACKEND/app/services/runtime_metrics.py" "$BACKUP/app/services/"
cp -a "$BACKEND/tests/test_api.py" "$BACKUP/tests/"
cp -a "$BACKEND/tests/test_runtime_metrics.py" "$BACKUP/tests/"
cp -a "$BACKEND/tests/test_scheduler_storage.py" "$BACKUP/tests/"
printf '%s\n' "$BACKUP" >/root/phase1_5_backup_path.txt

install -m 0644 "$PATCH/backend/app/api/routes.py" "$BACKEND/app/api/routes.py"
install -m 0644 "$PATCH/backend/app/core/config.py" "$BACKEND/app/core/config.py"
install -m 0644 "$PATCH/backend/app/services/runtime_metrics.py" "$BACKEND/app/services/runtime_metrics.py"
install -m 0644 "$PATCH/backend/tests/test_api.py" "$BACKEND/tests/test_api.py"
install -m 0644 "$PATCH/backend/tests/test_runtime_metrics.py" "$BACKEND/tests/test_runtime_metrics.py"
install -m 0644 "$PATCH/backend/tests/test_scheduler_storage.py" "$BACKEND/tests/test_scheduler_storage.py"
```

## Test before restart

```bash
cd "$BACKEND"
/opt/kinetics-gateway/venv/bin/python -m py_compile app/api/routes.py app/core/config.py app/services/runtime_metrics.py tests/test_api.py tests/test_runtime_metrics.py tests/test_scheduler_storage.py

time /opt/kinetics-gateway/venv/bin/python -m pytest tests/test_runtime_metrics.py::test_runtime_metrics_track_websocket_backpressure tests/test_api.py::test_websocket_defaults_to_delta_and_rejects_full_mode -q

time /opt/kinetics-gateway/venv/bin/python -m pytest tests/test_scheduler_storage.py tests/test_api.py tests/test_runtime_metrics.py -q
```

Expected: `2 passed`, then `17 passed`.

## Restart and readiness

```bash
date -Iseconds >/root/phase1_5_restart_time.txt
systemctl restart kinetics-gateway.service

for N in $(seq 1 150)
do
  RESULT=$(curl -sS --connect-timeout 1 --max-time 3 -w ' HTTP=%{http_code} TIME=%{time_total}' http://127.0.0.1:8000/api/health) || RESULT=REQUEST_FAILED
  echo "sample=$N $RESULT"
  echo "$RESULT" | grep -q '"ready":true' && break
  [ "$N" -lt 150 ] && sleep 1
done
```

## Authenticate and verify counters

```bash
LOGIN_RESPONSE=$(curl -fsS -X POST http://127.0.0.1:8000/api/auth/login -H 'Content-Type: application/json' -d '{"username":"internal","password":"Internal@123"}')
TOKEN=$(printf '%s' "$LOGIN_RESPONSE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
export TOKEN

curl -fsS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/diagnostics/runtime -o /tmp/phase15_runtime.json
python3 - <<'PY'
import json
d = json.load(open('/tmp/phase15_runtime.json'))
print(d['websockets'])
required = {'active', 'peak_active', 'accepted', 'disconnected', 'send_failures', 'rejected_clients', 'send_timeouts', 'backpressure_disconnects'}
assert required <= set(d['websockets'])
print('PASS: Phase 1.5 WebSocket counters present')
PY
```

## Ten-minute Flutter observation

Open Flutter in normal monitoring mode; do not send control commands.

```bash
for N in $(seq 1 10)
do
  echo "===== SAMPLE $N $(date -Iseconds) ====="
  curl -fsS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/diagnostics/runtime -o /tmp/phase15_runtime_sample.json
  python3 - <<'PY'
import json
d = json.load(open('/tmp/phase15_runtime_sample.json'))
print('websockets=', d['websockets'])
print('event_loop=', d['event_loop'])
PY
  curl -sS --connect-timeout 2 --max-time 5 -o /dev/null -w 'health status=%{http_code} seconds=%{time_total}\n' http://127.0.0.1:8000/api/health
  [ "$N" -lt 10 ] && sleep 60
done | tee /tmp/phase15_flutter_observation.txt
```

## Final evidence

```bash
systemctl show kinetics-gateway.service -p ActiveState -p SubState -p MainPID -p NRestarts -p MemoryCurrent -p MemoryPeak -p TasksCurrent --no-pager
systemctl is-enabled bess-seven-day-v302.service
systemctl is-active bess-seven-day-v302.service
journalctl -u kinetics-gateway.service --since "$(cat /root/phase1_5_restart_time.txt)" --no-pager -p warning
journalctl -k --since "$(cat /root/phase1_5_restart_time.txt)" --no-pager | grep -Ei 'oom|out of memory|killed process|segfault' || echo 'NO OOM OR KERNEL KILL FOUND'
cp -a /tmp/phase15_flutter_observation.txt /root/phase1_5_flutter_observation_passed.txt
```

## Rollback

```bash
BACKEND=/opt/kinetics-gateway/backend
BACKUP=$(cat /root/phase1_5_backup_path.txt)
cp -a "$BACKUP/app/api/routes.py" "$BACKEND/app/api/routes.py"
cp -a "$BACKUP/app/core/config.py" "$BACKEND/app/core/config.py"
cp -a "$BACKUP/app/services/runtime_metrics.py" "$BACKEND/app/services/runtime_metrics.py"
cp -a "$BACKUP/tests/test_api.py" "$BACKEND/tests/test_api.py"
cp -a "$BACKUP/tests/test_runtime_metrics.py" "$BACKEND/tests/test_runtime_metrics.py"
cp -a "$BACKUP/tests/test_scheduler_storage.py" "$BACKEND/tests/test_scheduler_storage.py"
systemctl restart kinetics-gateway.service
```
