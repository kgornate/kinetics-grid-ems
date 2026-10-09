#!/bin/sh
set -eu

PROJECT="${1:-/root/kinetics-grid-ems/northbound_ems_gateway}"
PATCH_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$PROJECT/backups/g10_d1_s9_${TS}"

cd "$PROJECT"

echo "=============================================================="
echo " G10 / D1 + S9 COMMAND LIFECYCLE PATCH - PRECHECK"
echo "=============================================================="

check_sha() {
    file="$1"
    expected="$2"
    actual="$(sha256sum "$file" | awk '{print $1}')"
    echo "$file"
    echo "  expected=$expected"
    echo "  actual  =$actual"
    if [ "$actual" != "$expected" ]; then
        echo "BASELINE_DRIFT=FAIL file=$file"
        exit 1
    fi
}

check_sha src/nb_ems_gateway/central_sync/config.py 0c6e8ec93cb2d6397c56b94d6caf61d8d35d704d2aa5fe39d31093f0966e3321
check_sha src/nb_ems_gateway/central_sync/client.py af222fa1cf7a71d1744e82a48761c13f6c02e12c1d2d1087311ad0b0a5d85259
check_sha src/nb_ems_gateway/central_sync/local_gateway_api.py 03b1e0ee9feaa2dfed7f1eee257857ba6b82607f8cdb61241a9b345731198268
check_sha src/nb_ems_gateway/central_sync/configuration_audit_producer.py 0f2cba4d8bc5fed3b26181c2d948192b0489a4be0cc536b20760ae168af36661
check_sha src/nb_ems_gateway/central_sync/service.py f8868703aeef3304bebd4fd290279b9ef79f08bc12c0549afdb616f291dfc3c1
check_sha configs/central_sync.json 2c610d691f92189814104e563c5519631172ca777b05529de237448ee6548bfc

echo "BASELINE_DRIFT=PASS"
mkdir -p "$BACKUP/src/nb_ems_gateway/central_sync" "$BACKUP/tools" "$BACKUP/configs"
for f in config.py client.py local_gateway_api.py configuration_audit_producer.py service.py; do
    cp "src/nb_ems_gateway/central_sync/$f" "$BACKUP/src/nb_ems_gateway/central_sync/"
done
cp configs/central_sync.json "$BACKUP/configs/"
[ -f src/nb_ems_gateway/central_sync/command_downlink.py ] && cp src/nb_ems_gateway/central_sync/command_downlink.py "$BACKUP/src/nb_ems_gateway/central_sync/" || true
[ -f tools/central_sync_d1_s9_inject.py ] && cp tools/central_sync_d1_s9_inject.py "$BACKUP/tools/" || true
[ -f tools/central_sync_g10_d1_s9_selftest.py ] && cp tools/central_sync_g10_d1_s9_selftest.py "$BACKUP/tools/" || true

echo "BACKUP=$BACKUP"

for f in config.py client.py local_gateway_api.py configuration_audit_producer.py command_downlink.py service.py; do
    install -m 0644 "$PATCH_DIR/src/nb_ems_gateway/central_sync/$f" "src/nb_ems_gateway/central_sync/$f"
done
install -m 0755 "$PATCH_DIR/tools/central_sync_d1_s9_inject.py" tools/central_sync_d1_s9_inject.py
install -m 0755 "$PATCH_DIR/tools/central_sync_g10_d1_s9_selftest.py" tools/central_sync_g10_d1_s9_selftest.py
install -m 0644 "$PATCH_DIR/docs/central_sync_g10_d1_s9.md" docs/central_sync_g10_d1_s9.md

python3 - <<'PY'
import json
from pathlib import Path
p=Path('configs/central_sync.json')
d=json.loads(p.read_text())
d.setdefault('identity', {})['software_version']='central-sync-g10-d1-s9-command-lifecycle'
d['command_downlink']={
    'enabled': False,
    'poll_path': '/api/v1/commands/poll',
    'poll_interval_sec': 3.0,
    'max_commands_per_poll': 10,
    'status_file': '/var/lib/nb-ems-central-sync/d1_command_downlink_status.json',
    'ledger_path': '/mnt/ems-logs/northbound_ems_gateway/d1_command_ledger.db',
    's9_stream': 'command_results',
    's9_substream': 'gateway',
    's9_priority': 'P0',
    'allowed_requested_role': 'internal_admin',
    'allowed_command_types': [
        'source_grid_mode','site_grid_mode','source_charge','source_discharge','source_standby',
        'site_power','site_standby','ems_register_write','ems_batch_write'
    ],
}
d.setdefault('backlog_replay', {})['enabled']=False
p.write_text(json.dumps(d, indent=2)+'\n')
PY

echo
echo "--- STATIC VALIDATION ---"
python3 -m py_compile \
  src/nb_ems_gateway/central_sync/config.py \
  src/nb_ems_gateway/central_sync/client.py \
  src/nb_ems_gateway/central_sync/local_gateway_api.py \
  src/nb_ems_gateway/central_sync/configuration_audit_producer.py \
  src/nb_ems_gateway/central_sync/command_downlink.py \
  src/nb_ems_gateway/central_sync/service.py \
  tools/central_sync_d1_s9_inject.py \
  tools/central_sync_g10_d1_s9_selftest.py

PYTHONPATH=src python3 tools/central_sync_g10_d1_s9_selftest.py
PYTHONPATH=src pytest -q

PYTHONPATH=src python3 - <<'PY'
from nb_ems_gateway.central_sync.config import load_central_sync_config
c=load_central_sync_config('configs/central_sync.json')
print('software_version =', c.identity.software_version)
print('S1 =', c.fast_bess.enabled)
print('S2 =', c.general_assets.enabled)
print('S3 =', c.gateway_health.enabled)
print('S4 =', c.alarms_events.enabled)
print('S5 =', c.soc_controller.enabled)
print('S6 =', c.solis.enabled)
print('S7 =', c.edge_ai.enabled)
print('S8 =', c.configuration_audit.enabled)
print('D1 installed =', hasattr(c, 'command_downlink'))
print('D1 enabled =', c.command_downlink.enabled)
print('D1 poll path =', c.command_downlink.poll_path)
print('S9 stream =', c.command_downlink.s9_stream)
print('S9 priority =', c.command_downlink.s9_priority)
print('uploader workers =', c.uploader.worker_count)
print('replay =', c.backlog_replay.enabled)
assert all([c.fast_bess.enabled,c.general_assets.enabled,c.gateway_health.enabled,c.alarms_events.enabled,c.soc_controller.enabled,c.solis.enabled,c.edge_ai.enabled,c.configuration_audit.enabled])
assert c.command_downlink.enabled is False
assert c.uploader.worker_count == 1
assert c.backlog_replay.enabled is False
print('G10_D1_S9_CONFIG=PASS')
PY

echo
echo "=============================================================="
echo " G10 / D1 + S9 PATCH INSTALL=PASS"
echo " D1 POLLING INSTALLED BUT REMAINS DISABLED"
echo " SERVICE WAS NOT RESTARTED BY THIS INSTALLER"
echo " BACKLOG REPLAY REMAINS OFF"
echo "=============================================================="
