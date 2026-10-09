#!/bin/sh
set -eu

PROJECT="${1:-/root/kinetics-grid-ems/northbound_ems_gateway}"
PATCH_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$PROJECT/backups/g11_store_forward_${TS}"

cd "$PROJECT"

echo "=============================================================="
echo " G11 STORE-AND-FORWARD RECOVERY PATCH - PRECHECK"
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

# Post-G9/S8 commissioned baseline source checks.
check_sha src/nb_ems_gateway/central_sync/config.py 0c6e8ec93cb2d6397c56b94d6caf61d8d35d704d2aa5fe39d31093f0966e3321
check_sha src/nb_ems_gateway/central_sync/service.py f8868703aeef3304bebd4fd290279b9ef79f08bc12c0549afdb616f291dfc3c1
check_sha src/nb_ems_gateway/central_sync/uploader.py 27142cf27905b5b06d092f64ed1b0c92aba6f575498e1ab1f64d2ceec81dc0eb
check_sha src/nb_ems_gateway/central_sync/outbox.py a83913e126eb75cc92055af097cf7096968d348407b7d9062a5f9f95a8c5a5f8
check_sha src/nb_ems_gateway/central_sync/batcher.py eccc80711e502635a763d87d03fec67f2986f7c75b9b5b63c0f068cd90cf512c
check_sha src/nb_ems_gateway/central_sync/overflow_archiver.py bdd5719775d04d8fc02caa857c50422b12a6f1750476e01f206cf4a3623943dd
check_sha src/nb_ems_gateway/central_sync/backlog_replayer.py 47667b766d54e7b8d799b60132bdc5cbbde154f7381d4fc1021cf7d441b78854
check_sha src/nb_ems_gateway/central_sync/configuration_audit_producer.py 0f2cba4d8bc5fed3b26181c2d948192b0489a4be0cc536b20760ae168af36661
check_sha tools/central_sync_live_dashboard.sh e5e59f618b4642b4c95c5b4a58aab652f83312d6bc10e72e492556ee7cd97b11
check_sha configs/central_sync.json 2c610d691f92189814104e563c5519631172ca777b05529de237448ee6548bfc

echo "BASELINE_DRIFT=PASS"

REPLAY_STATE="$(systemctl is-active central-sync-backlog-replay.service 2>/dev/null || true)"
echo "LEGACY_REPLAY_STATE=$REPLAY_STATE"
if [ "$REPLAY_STATE" = "active" ]; then
    echo "SAFETY_PRECHECK=FAIL legacy backlog replay service is active"
    exit 1
fi

echo
mkdir -p "$BACKUP/src/nb_ems_gateway/central_sync" "$BACKUP/tools" "$BACKUP/configs" "$BACKUP/docs"
cp src/nb_ems_gateway/central_sync/config.py "$BACKUP/src/nb_ems_gateway/central_sync/"
cp src/nb_ems_gateway/central_sync/service.py "$BACKUP/src/nb_ems_gateway/central_sync/"
cp src/nb_ems_gateway/central_sync/uploader.py "$BACKUP/src/nb_ems_gateway/central_sync/"
cp tools/central_sync_live_dashboard.sh "$BACKUP/tools/"
cp configs/central_sync.json "$BACKUP/configs/"
[ -f src/nb_ems_gateway/central_sync/transport_control.py ] && cp src/nb_ems_gateway/central_sync/transport_control.py "$BACKUP/src/nb_ems_gateway/central_sync/" || true
[ -f src/nb_ems_gateway/central_sync/overflow_recovery.py ] && cp src/nb_ems_gateway/central_sync/overflow_recovery.py "$BACKUP/src/nb_ems_gateway/central_sync/" || true
[ -f tools/central_sync_transport_control.sh ] && cp tools/central_sync_transport_control.sh "$BACKUP/tools/" || true
[ -f tools/central_sync_g11_store_forward_selftest.py ] && cp tools/central_sync_g11_store_forward_selftest.py "$BACKUP/tools/" || true
[ -f docs/central_sync_g11_store_forward_recovery.md ] && cp docs/central_sync_g11_store_forward_recovery.md "$BACKUP/docs/" || true

echo "BACKUP=$BACKUP"

install -m 0644 "$PATCH_DIR/src/nb_ems_gateway/central_sync/config.py" src/nb_ems_gateway/central_sync/config.py
install -m 0644 "$PATCH_DIR/src/nb_ems_gateway/central_sync/service.py" src/nb_ems_gateway/central_sync/service.py
install -m 0644 "$PATCH_DIR/src/nb_ems_gateway/central_sync/uploader.py" src/nb_ems_gateway/central_sync/uploader.py
install -m 0644 "$PATCH_DIR/src/nb_ems_gateway/central_sync/transport_control.py" src/nb_ems_gateway/central_sync/transport_control.py
install -m 0644 "$PATCH_DIR/src/nb_ems_gateway/central_sync/overflow_recovery.py" src/nb_ems_gateway/central_sync/overflow_recovery.py
install -m 0755 "$PATCH_DIR/tools/central_sync_transport_control.sh" tools/central_sync_transport_control.sh
install -m 0755 "$PATCH_DIR/tools/central_sync_live_dashboard.sh" tools/central_sync_live_dashboard.sh
install -m 0755 "$PATCH_DIR/tools/central_sync_g11_store_forward_selftest.py" tools/central_sync_g11_store_forward_selftest.py
install -m 0644 "$PATCH_DIR/docs/central_sync_g11_store_forward_recovery.md" docs/central_sync_g11_store_forward_recovery.md

python3 - <<'PY'
import json
from pathlib import Path
p=Path('configs/central_sync.json')
d=json.loads(p.read_text())
d.setdefault('identity', {})['software_version']='central-sync-g11-store-forward-recovery'
u=d.setdefault('uploader', {})
u['pause_file']='/var/lib/nb-ems-central-sync/uploader.pause'
u['pause_poll_sec']=1.0
d['overflow_recovery']={
    'enabled': True,
    'archive_dir': '/mnt/ems-logs/northbound_ems_gateway/backlog_archives',
    'archive_glob': 'central_sync_overflow_*.db',
    'status_file': '/var/lib/nb-ems-central-sync/overflow_recovery_status.json',
    'uploader_status_file': '/var/lib/nb-ems-central-sync/overflow_recovery_uploader_status.json',
    'marker_suffix': '.replayed.json',
    'scan_interval_sec': 5.0,
    'request_pause_sec': 10.0,
    'max_messages_per_request': 25,
    'max_request_bytes': 131072,
    'live_pause_sendable_count': 25,
    'live_pause_oldest_age_sec': 3.0,
    'min_available_memory_mb': 500,
    'max_load1': 2.0,
}
# Never enable the legacy historical backlog service as part of G11.
d.setdefault('backlog_replay', {})['enabled']=False
p.write_text(json.dumps(d, indent=2)+'\n')
PY

echo
echo "--- STATIC VALIDATION ---"
python3 -m py_compile \
  src/nb_ems_gateway/central_sync/config.py \
  src/nb_ems_gateway/central_sync/service.py \
  src/nb_ems_gateway/central_sync/uploader.py \
  src/nb_ems_gateway/central_sync/transport_control.py \
  src/nb_ems_gateway/central_sync/overflow_recovery.py \
  tools/central_sync_g11_store_forward_selftest.py

sh -n tools/central_sync_transport_control.sh
sh -n tools/central_sync_live_dashboard.sh

PYTHONPATH=src python3 tools/central_sync_g11_store_forward_selftest.py
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
print('live uploader workers =', c.uploader.worker_count)
print('transport pause file =', c.uploader.pause_file)
print('overflow recovery =', c.overflow_recovery.enabled)
print('overflow recovery glob =', c.overflow_recovery.archive_glob)
print('legacy backlog replay =', c.backlog_replay.enabled)
assert all([c.fast_bess.enabled,c.general_assets.enabled,c.gateway_health.enabled,c.alarms_events.enabled,c.soc_controller.enabled,c.solis.enabled,c.edge_ai.enabled,c.configuration_audit.enabled])
assert c.uploader.worker_count == 1
assert c.overflow_recovery.enabled is True
assert c.overflow_recovery.archive_glob == 'central_sync_overflow_*.db'
assert c.backlog_replay.enabled is False
print('G11_CONFIG=PASS')
PY

echo
echo "=============================================================="
echo " G11 STORE-AND-FORWARD PATCH INSTALL=PASS"
echo " SERVICE WAS NOT RESTARTED BY THIS INSTALLER"
echo " S1-S8 REMAIN ENABLED"
echo " LEGACY HISTORICAL BACKLOG REPLAY REMAINS OFF"
echo " USE tools/central_sync_transport_control.sh pause/resume"
echo "=============================================================="
