# Phase 1.4 FRDM Deployment, Validation and Rollback

Keep `bess-seven-day-v302.service` disabled and inactive throughout this phase.
Do not issue BESS or PCS control commands.

## 1. Copy patch from PC to FRDM

From Windows PowerShell, from the folder containing the archive:

```powershell
scp .\Kinetics_Gateway_Phase1_4_Historian_Lock_20260805.tar.gz root@192.168.10.2:/root/
```

## 2. Verify safety state and extract

```bash
systemctl is-enabled bess-seven-day-v302.service
systemctl is-active bess-seven-day-v302.service

rm -rf /tmp/kinetics_phase1_4_patch
mkdir -p /tmp/kinetics_phase1_4_patch
tar -xzf /root/Kinetics_Gateway_Phase1_4_Historian_Lock_20260805.tar.gz \
  -C /tmp/kinetics_phase1_4_patch
```

Expected scheduler state: `disabled` and `inactive`.

## 3. Back up the two replaced files

```bash
PHASE14_BACKUP=/root/kinetics_phase1_4_backup_$(date +%Y%m%d_%H%M%S)
mkdir -p "$PHASE14_BACKUP/app/services" "$PHASE14_BACKUP/tests"
cp -a /opt/kinetics-gateway/backend/app/services/gateway_service.py \
  "$PHASE14_BACKUP/app/services/"
cp -a /opt/kinetics-gateway/backend/tests/test_scheduler_storage.py \
  "$PHASE14_BACKUP/tests/"
printf '%s\n' "$PHASE14_BACKUP" >/root/phase1_4_backup_path.txt
```

## 4. Install over the Phase 1.3 baseline

```bash
PATCH=/tmp/kinetics_phase1_4_patch
BACKEND=/opt/kinetics-gateway/backend

install -m 0644 "$PATCH/backend/app/services/gateway_service.py" \
  "$BACKEND/app/services/gateway_service.py"
install -m 0644 "$PATCH/backend/tests/test_scheduler_storage.py" \
  "$BACKEND/tests/test_scheduler_storage.py"
```

This is an incremental patch. Install these files over the existing Phase 1.3
codebase; do not replace the complete backend directory.

## 5. Fast syntax and new regression test

```bash
cd /opt/kinetics-gateway/backend

/opt/kinetics-gateway/venv/bin/python -m py_compile \
  app/services/gateway_service.py \
  tests/test_scheduler_storage.py

time /opt/kinetics-gateway/venv/bin/python -m pytest \
  tests/test_scheduler_storage.py::test_historian_write_does_not_hold_gateway_cache_lock \
  -q
```

Stop and roll back if this test fails.

## 6. Focused Phase 1 regression suite

This suite takes several minutes on the FRDM. Run it once; do not repeatedly
restart pytest while it is working.

```bash
time /opt/kinetics-gateway/venv/bin/python -m pytest \
  tests/test_scheduler_storage.py \
  tests/test_api.py \
  tests/test_runtime_metrics.py \
  -q
```

Expected result after adding the new test: `15 passed`.

## 7. Restart once and wait for readiness

```bash
date -Iseconds >/root/phase1_4_restart_time.txt
systemctl restart kinetics-gateway.service

for N in $(seq 1 120)
do
  RESULT=$(curl -sS --connect-timeout 1 --max-time 3 \
    -w ' HTTP=%{http_code} TIME=%{time_total}' \
    http://127.0.0.1:8000/api/health) || RESULT=REQUEST_FAILED
  echo "sample=$N $RESULT"
  echo "$RESULT" | grep -q '"ready":true' && break
  [ "$N" -lt 120 ] && sleep 1
done
```

The longer wait ceiling preserves the already-observed pre-listening startup
behaviour for this phase; Phase 1.4 does not change startup semantics.

## 8. Obtain a token safely

```bash
LOGIN_RESPONSE=$(curl -fsS --connect-timeout 3 --max-time 20 \
  -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"internal","password":"Internal@123"}') || {
    echo 'ERROR: Login request failed'
    LOGIN_RESPONSE=
  }

if [ -n "$LOGIN_RESPONSE" ]; then
  TOKEN=$(printf '%s' "$LOGIN_RESPONSE" | \
    python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
  export TOKEN
  echo "TOKEN length=${#TOKEN}"
fi
```

## 9. Observe historian progress and health latency

```bash
for N in $(seq 1 10)
do
  echo "===== SAMPLE $N $(date -Iseconds) ====="

  curl -fsS --connect-timeout 2 --max-time 5 \
    -H "Authorization: Bearer $TOKEN" \
    http://127.0.0.1:8000/api/diagnostics/runtime \
    -o /tmp/phase14_runtime.json

  python3 - <<'PY'
import json
d = json.load(open('/tmp/phase14_runtime.json'))
print('historian=', d.get('background', {}).get('historian-write'))
print('http_in_flight=', d.get('http', {}).get('in_flight'))
print('event_loop=', d.get('event_loop'))
PY

  curl -sS --connect-timeout 2 --max-time 5 -o /dev/null \
    -w 'health status=%{http_code} seconds=%{time_total}\n' \
    http://127.0.0.1:8000/api/health

  [ "$N" -lt 10 ] && sleep 10
done | tee /tmp/phase14_historian_observation.txt
```

Pass conditions: historian count increases, errors remain zero, all health
responses are HTTP 200, and each health response is below 0.5 seconds.

## 10. Final evidence

```bash
systemctl show kinetics-gateway.service \
  -p ActiveState -p SubState -p MainPID -p NRestarts \
  -p MemoryCurrent -p MemoryPeak -p TasksCurrent --no-pager

systemctl is-enabled bess-seven-day-v302.service
systemctl is-active bess-seven-day-v302.service

journalctl -u kinetics-gateway.service \
  --since "$(cat /root/phase1_4_restart_time.txt)" \
  --no-pager -p warning
```

## Rollback

```bash
BACKUP=$(cat /root/phase1_4_backup_path.txt)
BACKEND=/opt/kinetics-gateway/backend

cp -a "$BACKUP/app/services/gateway_service.py" \
  "$BACKEND/app/services/gateway_service.py"
cp -a "$BACKUP/tests/test_scheduler_storage.py" \
  "$BACKEND/tests/test_scheduler_storage.py"

systemctl restart kinetics-gateway.service
systemctl status kinetics-gateway.service --no-pager -l
```
