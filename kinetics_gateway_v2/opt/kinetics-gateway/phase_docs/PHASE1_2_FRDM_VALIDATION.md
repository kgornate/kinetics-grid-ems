# Phase 1.2 FRDM Validation

Keep `bess-seven-day-v302.service` disabled and do not perform BESS control
during this diagnostic validation.

## 1. Pre-deployment checks

```bash
systemctl is-active kinetics-gateway.service
systemctl is-enabled bess-seven-day-v302.service
systemctl is-active bess-seven-day-v302.service
```

Expected scheduler state for this phase: `disabled` and `inactive`.

## 2. Deploy and restart

Back up the current file before replacement:

```bash
cp -a \
  /opt/kinetics-gateway/backend/app/services/runtime_metrics.py \
  /opt/kinetics-gateway/backend/app/services/runtime_metrics.py.phase1_1_backup
```

After copying the Phase 1.2 file into place:

```bash
/opt/kinetics-gateway/venv/bin/python -m py_compile \
  /opt/kinetics-gateway/backend/app/services/runtime_metrics.py

systemctl restart kinetics-gateway.service
systemctl is-active kinetics-gateway.service
```

## 3. Obtain the internal token

```bash
TOKEN=$(curl -fsS --connect-timeout 3 --max-time 20 \
  -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"internal","password":"Internal@123"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

export TOKEN
echo "TOKEN length=${#TOKEN}"
```

## 4. Verify the new structure

```bash
curl -fsS --connect-timeout 3 --max-time 10 \
  -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/diagnostics/runtime \
  -o /tmp/phase1_2_runtime.json

python3 -m json.tool /tmp/phase1_2_runtime.json
```

```bash
python3 - <<'PY'
import json

d = json.load(open('/tmp/phase1_2_runtime.json'))
assert 'breakdown' in d['process']
assert 'cgroup' in d
assert 'available' in d['cgroup']
print('PASS: Phase 1.2 memory attribution structure is valid')
print('Process:', d['process'])
print('Cgroup:', d['cgroup'])
PY
```

On this FRDM image, `cgroup.available` should normally be `true`.

## 5. Collect ten one-minute samples

```bash
PHASE12_RESULTS=/mnt/ems-logs/phase1-validation/phase1_2_$(date +%Y%m%d_%H%M%S)
mkdir -p "$PHASE12_RESULTS"
echo "$PHASE12_RESULTS" >/root/phase1_2_results_path.txt

for N in $(seq 1 10)
do
  curl -fsS --connect-timeout 3 --max-time 10 \
    -H "Authorization: Bearer $TOKEN" \
    http://127.0.0.1:8000/api/diagnostics/runtime \
    -o "$PHASE12_RESULTS/runtime_$(printf '%02d' "$N").json" || \
    echo "sample $N failed" >>"$PHASE12_RESULTS/failures.txt"

  echo "Completed sample $N/10"
  if [ "$N" -lt 10 ]; then sleep 60; fi
done
```

## 6. Print the attribution summary

```bash
PHASE12_RESULTS=$(cat /root/phase1_2_results_path.txt)
PHASE12_RESULTS="$PHASE12_RESULTS" python3 - <<'PY'
import glob, json, os

paths = sorted(glob.glob(os.path.join(os.environ['PHASE12_RESULTS'], 'runtime_*.json')))
for path in paths:
    d = json.load(open(path))
    p = d['process']
    c = d['cgroup']
    b = c.get('breakdown', {})
    mib = lambda value: None if value is None else round(value / 1048576, 2)
    print({
        'sample': os.path.basename(path),
        'process_rss_mib': mib(p.get('rss_bytes')),
        'cgroup_current_mib': mib(c.get('current_bytes')),
        'cgroup_anon_mib': mib(b.get('anon_bytes')),
        'cgroup_file_mib': mib(b.get('file_bytes')),
        'cgroup_kernel_mib': mib(b.get('kernel_bytes')),
        'cgroup_slab_mib': mib(b.get('slab_bytes')),
        'processes': c.get('process_count'),
        'threads': c.get('thread_count'),
        'events': c.get('events'),
    })
PY
```

Send the ten-line summary and `runtime_10.json` for interpretation. Remove the
token afterward:

```bash
unset TOKEN
```

## Rollback

```bash
cp -a \
  /opt/kinetics-gateway/backend/app/services/runtime_metrics.py.phase1_1_backup \
  /opt/kinetics-gateway/backend/app/services/runtime_metrics.py

systemctl restart kinetics-gateway.service
```
