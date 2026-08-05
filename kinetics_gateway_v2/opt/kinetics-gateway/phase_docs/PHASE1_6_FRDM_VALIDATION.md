# Phase 1.6 FRDM Installation and Validation

Install only over the formally approved Phase 1.5 baseline. This is monitoring-only: do not charge or discharge, and keep `bess-seven-day-v302.service` disabled/inactive.

## 1. Verify and extract

```bash
sha256sum /root/Kinetics_Gateway_Phase1_6_HTTP_Admission_20260805.tar.gz
systemctl is-enabled bess-seven-day-v302.service
systemctl is-active bess-seven-day-v302.service

rm -rf /tmp/kinetics_phase1_6_patch
mkdir -p /tmp/kinetics_phase1_6_patch
tar -xzf /root/Kinetics_Gateway_Phase1_6_HTTP_Admission_20260805.tar.gz \
  -C /tmp/kinetics_phase1_6_patch
find /tmp/kinetics_phase1_6_patch -type f -print | sort
```

Expected scheduler state: `disabled` and `inactive`.

## 2. Back up Phase 1.5

```bash
BACKEND=/opt/kinetics-gateway/backend
PATCH=/tmp/kinetics_phase1_6_patch
BACKUP="/root/kinetics_phase1_6_backup_$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP/app/core" "$BACKUP/app/services" "$BACKUP/tests"
cp -a "$BACKEND/app/main.py" "$BACKUP/app/"
cp -a "$BACKEND/app/core/config.py" "$BACKUP/app/core/"
cp -a "$BACKEND/app/services/runtime_metrics.py" "$BACKUP/app/services/"
cp -a "$BACKEND/tests/test_runtime_metrics.py" "$BACKUP/tests/"
printf '%s\n' "$BACKUP" >/root/phase1_6_backup_path.txt
find "$BACKUP" -type f -exec ls -lh {} \;
```

The two Phase 1.6 files `http_admission.py` and `test_http_admission.py` are new and therefore absent from the Phase 1.5 backup.

## 3. Install

```bash
install -m 0644 "$PATCH/backend/app/main.py" "$BACKEND/app/main.py"
install -m 0644 "$PATCH/backend/app/core/config.py" "$BACKEND/app/core/config.py"
install -m 0644 "$PATCH/backend/app/services/runtime_metrics.py" "$BACKEND/app/services/runtime_metrics.py"
install -m 0644 "$PATCH/backend/app/services/http_admission.py" "$BACKEND/app/services/http_admission.py"
install -m 0644 "$PATCH/backend/tests/test_runtime_metrics.py" "$BACKEND/tests/test_runtime_metrics.py"
install -m 0644 "$PATCH/backend/tests/test_http_admission.py" "$BACKEND/tests/test_http_admission.py"
```

## 4. Validate before restart

```bash
cd /opt/kinetics-gateway/backend

/opt/kinetics-gateway/venv/bin/python -m py_compile \
  app/main.py app/core/config.py app/services/runtime_metrics.py \
  app/services/http_admission.py tests/test_runtime_metrics.py \
  tests/test_http_admission.py

time /opt/kinetics-gateway/venv/bin/python -m pytest \
  tests/test_http_admission.py \
  tests/test_runtime_metrics.py::test_runtime_metrics_track_http_admission -q
```

Expected targeted result: `3 passed`.

```bash
time /opt/kinetics-gateway/venv/bin/python -m pytest \
  tests/test_scheduler_storage.py tests/test_api.py \
  tests/test_runtime_metrics.py tests/test_http_admission.py -q
```

Expected from the approved Phase 1.5 suite plus three new tests: `21 passed`. Stop before restart if any test fails.

## 5. Restart and wait for readiness

```bash
date -Iseconds >/root/phase1_6_restart_time.txt
systemctl restart kinetics-gateway.service
systemctl status kinetics-gateway.service --no-pager -l

for N in $(seq 1 150)
do
  RESULT=$(curl -sS --connect-timeout 1 --max-time 3 \
    -w ' HTTP=%{http_code} TIME=%{time_total}' \
    http://127.0.0.1:8000/api/health) || RESULT="REQUEST_FAILED"
  echo "sample=$N $RESULT"
  echo "$RESULT" | grep -q '"ready":true' && break
  [ "$N" -lt 150 ] && sleep 1
done | tee /tmp/phase16_readiness.txt
```

A successful sample contains `"ready":true` and `HTTP=200`.

## 6. Login and verify counters

```bash
LOGIN_RESPONSE=$(curl -fsS --connect-timeout 3 --max-time 20 \
  -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"internal","password":"Internal@123"}')

TOKEN=$(printf '%s' "$LOGIN_RESPONSE" | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
export TOKEN
python3 -c 'import os; print("TOKEN length=", len(os.environ["TOKEN"]))'

curl -fsS --connect-timeout 2 --max-time 5 \
  -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/diagnostics/runtime \
  -o /tmp/phase16_runtime_initial.json

python3 - <<'PY'
import json
d = json.load(open('/tmp/phase16_runtime_initial.json'))
a = d['http']['admission']
print('admission =', a)
print('baseline_rss_bytes =', d['process']['rss_bytes'])
print('baseline_cgroup_current_bytes =', d['cgroup'].get('current_bytes'))
required = {
    'active', 'peak_active', 'active_general', 'active_priority',
    'accepted', 'accepted_general', 'accepted_priority',
    'rejected', 'rejected_general', 'rejected_priority',
}
assert required <= set(a)
print('PASS: Phase 1.6 admission counters present')
PY
```

Preserve the pre-load memory baseline:

```bash
cp -a /tmp/phase16_runtime_initial.json /root/phase1_6_runtime_before_load.json
```

## 7. Flutter and read-only overload test

Open Flutter and keep it in monitoring-only mode. Do not issue control commands.

The load test below performs authenticated historian reads only. It makes no Modbus write and no control action.

```bash
rm -f /tmp/phase16_load_codes.txt /tmp/phase16_health_under_load.txt

(
  for N in $(seq 1 40)
  do
    curl -sS --connect-timeout 2 --max-time 20 \
      -H "Authorization: Bearer $TOKEN" \
      -o /dev/null -w '%{http_code} %{time_total}\n' \
      'http://127.0.0.1:8000/api/historian/bms_bank?limit=5000' &
  done
  wait
) >/tmp/phase16_load_codes.txt &
LOAD_PID=$!

for N in $(seq 1 30)
do
  curl -sS --connect-timeout 1 --max-time 3 \
    -o /dev/null -w "sample=$N status=%{http_code} seconds=%{time_total}\n" \
    http://127.0.0.1:8000/api/health
  sleep 0.2
done | tee /tmp/phase16_health_under_load.txt

wait "$LOAD_PID"

echo 'Historian response summary:'
awk '{count[$1]++} END {for (code in count) print code, count[code]}' \
  /tmp/phase16_load_codes.txt | sort
```

Pass conditions:

- All 30 reserved-capacity health probes return HTTP 200 without timeout; target below 0.5 seconds.
- Historian requests return only 200 or controlled 503 responses.
- A 503 proves load shedding. All-200 is also acceptable if requests finish before capacity fills.
- Flutter remains connected and refreshing.

```bash
curl -fsS --connect-timeout 2 --max-time 5 \
  -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/diagnostics/runtime \
  -o /tmp/phase16_runtime_after_load.json

python3 - <<'PY'
import json
d = json.load(open('/tmp/phase16_runtime_after_load.json'))
print('http =', d['http']['admission'])
print('websockets =', d['websockets'])
print('event_loop =', d['event_loop'])
print('process =', d['process'])
print('cgroup =', d['cgroup'])
assert d['http']['admission']['peak_active'] <= 12
print('PASS: admitted HTTP work stayed within total capacity')
PY
```

Wait 60 seconds after the burst so completed response objects and temporary
buffers can be released, then capture recovery memory:

```bash
sleep 60

curl -fsS --connect-timeout 2 --max-time 5 \
  -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/diagnostics/runtime \
  -o /tmp/phase16_runtime_recovery.json

python3 - <<'PY'
import json

before = json.load(open('/root/phase1_6_runtime_before_load.json'))
after = json.load(open('/tmp/phase16_runtime_recovery.json'))

before_rss = before['process']['rss_bytes']
after_rss = after['process']['rss_bytes']
before_cgroup = before['cgroup'].get('current_bytes')
after_cgroup = after['cgroup'].get('current_bytes')

print('before_rss_bytes =', before_rss)
print('recovery_rss_bytes =', after_rss)
print('rss_delta_bytes =', after_rss - before_rss)
print('before_cgroup_current_bytes =', before_cgroup)
print('recovery_cgroup_current_bytes =', after_cgroup)
if before_cgroup is not None and after_cgroup is not None:
    print('cgroup_delta_bytes =', after_cgroup - before_cgroup)
PY
```

This is attribution evidence, not an automatic strict pass/fail threshold.
Phase 1.6 must prevent unbounded growth; a retained baseline that remains high
will be investigated during Phase 1.7/1.8 before the final Phase 1 soak.

## 8. Ten-minute normal Flutter observation

```bash
for N in $(seq 1 10)
do
  echo "===== SAMPLE $N $(date -Iseconds) ====="
  curl -fsS --connect-timeout 2 --max-time 5 \
    -H "Authorization: Bearer $TOKEN" \
    http://127.0.0.1:8000/api/diagnostics/runtime \
    -o /tmp/phase16_runtime_sample.json
  python3 - <<'PY'
import json
d = json.load(open('/tmp/phase16_runtime_sample.json'))
print('admission =', d['http']['admission'])
print('websockets =', d['websockets'])
print('event_loop =', d['event_loop'])
print('rss_bytes =', d['process']['rss_bytes'])
print('cgroup_current_bytes =', d['cgroup'].get('current_bytes'))
PY
  curl -sS --connect-timeout 2 --max-time 5 -o /dev/null \
    -w 'health status=%{http_code} seconds=%{time_total}\n' \
    http://127.0.0.1:8000/api/health
  [ "$N" -lt 10 ] && sleep 60
done | tee /tmp/phase16_flutter_observation.txt
```

Pass: health remains HTTP 200 and responsive; active/peak admitted work remains bounded; Flutter continues refreshing; event-loop lag and memory do not continuously grow; gateway does not restart.

## 9. Final evidence

```bash
systemctl show kinetics-gateway.service \
  -p ActiveState -p SubState -p MainPID -p NRestarts \
  -p MemoryCurrent -p MemoryPeak -p TasksCurrent --no-pager

systemctl is-enabled bess-seven-day-v302.service
systemctl is-active bess-seven-day-v302.service

journalctl -u kinetics-gateway.service \
  --since "$(cat /root/phase1_6_restart_time.txt)" --no-pager -p warning

journalctl -k --since "$(cat /root/phase1_6_restart_time.txt)" --no-pager |
  grep -Ei 'oom|out of memory|killed process|segfault' ||
  echo 'NO OOM OR KERNEL KILL FOUND'

cp -a /tmp/phase16_readiness.txt /root/phase1_6_readiness_passed.txt
cp -a /tmp/phase16_load_codes.txt /root/phase1_6_load_codes.txt
cp -a /tmp/phase16_health_under_load.txt /root/phase1_6_health_under_load.txt
cp -a /tmp/phase16_runtime_after_load.json /root/phase1_6_runtime_after_load.json
cp -a /tmp/phase16_runtime_recovery.json /root/phase1_6_runtime_recovery.json
cp -a /tmp/phase16_flutter_observation.txt /root/phase1_6_flutter_observation.txt
```

Expected: active/running, `NRestarts=0`, scheduler disabled/inactive, no application exceptions, and no OOM/kernel kill. Deliberate controlled 503 access responses during the load window are acceptable.

## Rollback only on failure

```bash
BACKEND=/opt/kinetics-gateway/backend
BACKUP=$(cat /root/phase1_6_backup_path.txt)

cp -a "$BACKUP/app/main.py" "$BACKEND/app/main.py"
cp -a "$BACKUP/app/core/config.py" "$BACKEND/app/core/config.py"
cp -a "$BACKUP/app/services/runtime_metrics.py" "$BACKEND/app/services/runtime_metrics.py"
cp -a "$BACKUP/tests/test_runtime_metrics.py" "$BACKEND/tests/test_runtime_metrics.py"
rm -f "$BACKEND/app/services/http_admission.py"
rm -f "$BACKEND/tests/test_http_admission.py"
systemctl restart kinetics-gateway.service
systemctl status kinetics-gateway.service --no-pager -l
```
