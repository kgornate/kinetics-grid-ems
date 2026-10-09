#!/bin/sh
set -eu

PROJECT="${1:-/root/kinetics-grid-ems/northbound_ems_gateway}"
PATCH_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$PROJECT/backups/g9_s8_${TS}"

cd "$PROJECT"

echo "=============================================================="
echo " G9 / S8 CONFIGURATION AUDIT PATCH - PRECHECK"
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

check_sha src/nb_ems_gateway/central_sync/config.py 72998c639081e68e4763828ea6143b906981ae8e9a8f3334eb51b1758084366b
check_sha src/nb_ems_gateway/central_sync/service.py fb00586709d0cb213fb07a46a02f9f04bbde8ccb60c7ab2abe19d85c63244e9d
check_sha tools/central_sync_live_dashboard.sh b0f35856db2a518cb3a11907dc74f4587db874737f571d1a865b1db3ebf4c8dc

echo "BASELINE_DRIFT=PASS"

echo
mkdir -p "$BACKUP/src/nb_ems_gateway/central_sync" "$BACKUP/tools" "$BACKUP/configs"
cp src/nb_ems_gateway/central_sync/config.py "$BACKUP/src/nb_ems_gateway/central_sync/"
cp src/nb_ems_gateway/central_sync/service.py "$BACKUP/src/nb_ems_gateway/central_sync/"
cp tools/central_sync_live_dashboard.sh "$BACKUP/tools/"
cp configs/central_sync.json "$BACKUP/configs/"
[ -f src/nb_ems_gateway/central_sync/configuration_audit_producer.py ] && cp src/nb_ems_gateway/central_sync/configuration_audit_producer.py "$BACKUP/src/nb_ems_gateway/central_sync/" || true
[ -f tools/central_sync_g9_s8_selftest.py ] && cp tools/central_sync_g9_s8_selftest.py "$BACKUP/tools/" || true

echo "BACKUP=$BACKUP"

install -m 0644 "$PATCH_DIR/src/nb_ems_gateway/central_sync/config.py" src/nb_ems_gateway/central_sync/config.py
install -m 0644 "$PATCH_DIR/src/nb_ems_gateway/central_sync/service.py" src/nb_ems_gateway/central_sync/service.py
install -m 0644 "$PATCH_DIR/src/nb_ems_gateway/central_sync/configuration_audit_producer.py" src/nb_ems_gateway/central_sync/configuration_audit_producer.py
install -m 0755 "$PATCH_DIR/tools/central_sync_g9_s8_selftest.py" tools/central_sync_g9_s8_selftest.py
install -m 0755 "$PATCH_DIR/tools/central_sync_live_dashboard.sh" tools/central_sync_live_dashboard.sh
install -m 0644 "$PATCH_DIR/docs/central_sync_g9_s8_configuration_audit.md" docs/central_sync_g9_s8_configuration_audit.md

python3 - <<'PY'
import json
from pathlib import Path
p=Path('configs/central_sync.json')
d=json.loads(p.read_text())
d.setdefault('identity', {})['software_version']='central-sync-g9-s8-config-audit'
d['configuration_audit']={
    'enabled': True,
    'stream': 'configuration_audit',
    'substream': 'gateway',
    'poll_interval_sec': 1.0,
    'priority': 'P1',
    'controller_settings_path': '/var/lib/nb-ems-soc-solis-controller/control_settings.json',
    'controller_status_path': '/var/lib/nb-ems-soc-solis-controller/operator_status.json',
    'model_manifest_path': '/root/kinetics-grid-ems/northbound_ems_gateway/edge_ai_poc/runtime_v0_3/phase7_runtime_bundle_v0_3/model/ml_model_manifest_v0_3.json',
    'state_file': '/var/lib/nb-ems-central-sync/s8_configuration_audit_state.json',
    'status_file': '/var/lib/nb-ems-central-sync/s8_configuration_audit_producer_status.json',
}
# Safety invariant: this patch must never enable historical replay.
d.setdefault('backlog_replay', {})['enabled']=False
p.write_text(json.dumps(d, indent=2)+'\n')
PY

echo
echo "--- STATIC VALIDATION ---"
python3 -m py_compile \
  src/nb_ems_gateway/central_sync/configuration_audit_producer.py \
  src/nb_ems_gateway/central_sync/config.py \
  src/nb_ems_gateway/central_sync/service.py \
  tools/central_sync_g9_s8_selftest.py

PYTHONPATH=src python3 tools/central_sync_g9_s8_selftest.py
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
print('S8 stream =', c.configuration_audit.stream)
print('S8 priority =', c.configuration_audit.priority)
print('replay =', c.backlog_replay.enabled)
assert all([c.fast_bess.enabled,c.general_assets.enabled,c.gateway_health.enabled,c.alarms_events.enabled,c.soc_controller.enabled,c.solis.enabled,c.edge_ai.enabled,c.configuration_audit.enabled])
assert c.uploader.worker_count == 1
assert c.backlog_replay.enabled is False
print('G9_S8_CONFIG=PASS')
PY

echo
echo "=============================================================="
echo " G9 / S8 PATCH INSTALL=PASS"
echo " SERVICE WAS NOT RESTARTED BY THIS INSTALLER"
echo " BACKLOG REPLAY REMAINS OFF"
echo "=============================================================="
