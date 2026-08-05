# Phase 1.3 FRDM Deployment, Validation and Rollback

Use the commands below from an FRDM root shell. Keep Flutter in monitoring-only
mode and keep `bess-seven-day-v302.service` disabled and inactive.

## 1. Confirm scheduler state

```bash
systemctl is-enabled bess-seven-day-v302.service
systemctl is-active bess-seven-day-v302.service
```

Expected: `disabled`, then `inactive`.

## 2. Back up installed files

```bash
PHASE13_BACKUP=/root/kinetics_phase1_3_backup_$(date +%Y%m%d_%H%M%S)
mkdir -p "$PHASE13_BACKUP/app/api" "$PHASE13_BACKUP/app/services" "$PHASE13_BACKUP/tests"
cp -a /opt/kinetics-gateway/backend/app/main.py "$PHASE13_BACKUP/app/"
cp -a /opt/kinetics-gateway/backend/app/api/routes.py "$PHASE13_BACKUP/app/api/"
cp -a /opt/kinetics-gateway/backend/app/services/gateway_service.py "$PHASE13_BACKUP/app/services/"
cp -a /opt/kinetics-gateway/backend/tests/test_scheduler_storage.py "$PHASE13_BACKUP/tests/"
echo "$PHASE13_BACKUP" >/root/phase1_3_backup_path.txt
```

## 3. Install and test

```bash
PATCH=/root/phase1_3_patch/phase1
BACKEND=/opt/kinetics-gateway/backend

install -m 0644 "$PATCH/backend/app/main.py" "$BACKEND/app/main.py"
install -m 0644 "$PATCH/backend/app/api/routes.py" "$BACKEND/app/api/routes.py"
install -m 0644 "$PATCH/backend/app/services/gateway_service.py" "$BACKEND/app/services/gateway_service.py"
install -m 0644 "$PATCH/backend/tests/test_scheduler_storage.py" "$BACKEND/tests/test_scheduler_storage.py"

cd "$BACKEND"
/opt/kinetics-gateway/venv/bin/python -m py_compile \
  app/main.py app/api/routes.py app/services/gateway_service.py
/opt/kinetics-gateway/venv/bin/python -m pytest \
  tests/test_scheduler_storage.py tests/test_api.py tests/test_runtime_metrics.py -q
```

Do not restart if compilation or tests fail.

## 4. Restart and obtain token

```bash
systemctl restart kinetics-gateway.service
systemctl is-active kinetics-gateway.service
systemctl status kinetics-gateway.service --no-pager -l

TOKEN=$(curl -fsS --connect-timeout 3 --max-time 20 \
  -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"internal","password":"Internal@123"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
export TOKEN
```

## 5. Verify readiness and API structure

```bash
for N in $(seq 1 30); do
  READY=$(curl -fsS --max-time 3 http://127.0.0.1:8000/api/health \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("startup",{}).get("ready"))' 2>/dev/null) || true
  echo "startup sample=$N ready=$READY"
  [ "$READY" = "True" ] && break
  sleep 1
done

curl -fsS --max-time 5 -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/bms/racks/summary \
  | python3 -m json.tool
```

## 6. Ten-minute Flutter-loaded latency sampling

Start Flutter locally, leave normal monitoring open, and issue no control
commands. Then run:

```bash
PHASE13_RESULTS=/mnt/ems-logs/phase1-validation/phase1_3_$(date +%Y%m%d_%H%M%S)
mkdir -p "$PHASE13_RESULTS"
echo "$PHASE13_RESULTS" >/root/phase1_3_results_path.txt

for N in $(seq 1 10); do
  OUT="$PHASE13_RESULTS/latency_$(printf '%02d' "$N").txt"
  for PATH in \
    api/health \
    api/diagnostics/polling \
    api/diagnostics/data-rate \
    api/storage/status \
    api/bms/racks/summary
  do
    curl -sS -o /dev/null --connect-timeout 3 --max-time 5 \
      -H "Authorization: Bearer $TOKEN" \
      -w "$PATH status=%{http_code} seconds=%{time_total}\n" \
      "http://127.0.0.1:8000/$PATH" >>"$OUT" || echo "$PATH FAILED" >>"$OUT"
  done
  curl -fsS --max-time 5 -H "Authorization: Bearer $TOKEN" \
    http://127.0.0.1:8000/api/diagnostics/runtime \
    -o "$PHASE13_RESULTS/runtime_$(printf '%02d' "$N").json"
  echo "Completed sample $N/10"
  [ "$N" -lt 10 ] && sleep 60
done
```

## 7. Print results

```bash
PHASE13_RESULTS=$(cat /root/phase1_3_results_path.txt)
cat "$PHASE13_RESULTS"/latency_*.txt
python3 -m json.tool "$PHASE13_RESULTS/runtime_10.json"
systemctl show kinetics-gateway.service \
  -p MainPID -p NRestarts -p MemoryCurrent -p MemoryPeak -p TasksCurrent --no-pager
systemctl is-enabled bess-seven-day-v302.service
systemctl is-active bess-seven-day-v302.service
unset TOKEN
```

Send the latency lines, `runtime_10.json`, final `systemctl show`, and scheduler
state for the Phase 1.3 pass decision.

## Rollback

```bash
PHASE13_BACKUP=$(cat /root/phase1_3_backup_path.txt)
BACKEND=/opt/kinetics-gateway/backend
cp -a "$PHASE13_BACKUP/app/main.py" "$BACKEND/app/main.py"
cp -a "$PHASE13_BACKUP/app/api/routes.py" "$BACKEND/app/api/routes.py"
cp -a "$PHASE13_BACKUP/app/services/gateway_service.py" "$BACKEND/app/services/gateway_service.py"
cp -a "$PHASE13_BACKUP/tests/test_scheduler_storage.py" "$BACKEND/tests/test_scheduler_storage.py"
systemctl restart kinetics-gateway.service
systemctl status kinetics-gateway.service --no-pager -l
```
