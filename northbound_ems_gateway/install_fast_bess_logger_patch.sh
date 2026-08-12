#!/bin/sh
set -e

GW_DIR="/root/kinetics-grid-ems/northbound_ems_gateway"
PATCH_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
FILES_DIR="$PATCH_DIR/files/northbound_ems_gateway"
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="/root/kinetics-grid-ems/northbound_ems_gateway_before_fast_bess_${TS}"

if [ ! -d "$GW_DIR" ]; then
  echo "ERROR: gateway directory not found: $GW_DIR" >&2
  exit 1
fi

if [ ! -d "$FILES_DIR" ]; then
  echo "ERROR: patch files not found: $FILES_DIR" >&2
  exit 1
fi

echo "Stopping services..."
systemctl stop ems-v3-soc-controller.service 2>/dev/null || true
systemctl stop ems-v3-gateway.service 2>/dev/null || true

echo "Creating backup: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"
for f in \
  configs/development.json \
  data/historian_profiles/fast_bess_profiles.json \
  src/nb_ems_gateway/config/models.py \
  src/nb_ems_gateway/storage/sqlite_store.py \
  src/nb_ems_gateway/storage/fast_bess_logger.py \
  src/nb_ems_gateway/polling/scheduler.py \
  src/nb_ems_gateway/app/dependency_container.py \
  src/nb_ems_gateway/main.py \
  src/nb_ems_gateway/api/routes_fast_bess.py \
  src/nb_ems_gateway/api/routes_health.py \
  src/nb_ems_gateway/api/server.py
 do
  if [ -e "$GW_DIR/$f" ]; then
    mkdir -p "$BACKUP_DIR/$(dirname "$f")"
    cp -a "$GW_DIR/$f" "$BACKUP_DIR/$f"
  fi
 done

echo "Installing patch files..."
cp -a "$FILES_DIR/." "$GW_DIR/"

mkdir -p /mnt/ems-logs/northbound_ems_gateway

echo "Validating Python syntax and config..."
cd "$GW_DIR"
PYTHONPATH=src python3 -m py_compile \
  src/nb_ems_gateway/config/models.py \
  src/nb_ems_gateway/storage/sqlite_store.py \
  src/nb_ems_gateway/storage/fast_bess_logger.py \
  src/nb_ems_gateway/polling/scheduler.py \
  src/nb_ems_gateway/app/dependency_container.py \
  src/nb_ems_gateway/main.py \
  src/nb_ems_gateway/api/routes_fast_bess.py \
  src/nb_ems_gateway/api/routes_health.py \
  src/nb_ems_gateway/api/server.py

PYTHONPATH=src python3 - <<'PY'
from nb_ems_gateway.config.loader import load_config
from nb_ems_gateway.dictionary.register_map import RegisterMap
import json
c = load_config('configs/development.json')
r = RegisterMap.load(c.register_map.path)
profile = json.load(open(c.fast_bess_logger.profile_path))['profiles'][c.fast_bess_logger.profile_name]['assets']
for asset, names in profile.items():
    existing = {p.signal_name for p in r.points if p.asset_id == asset}
    missing = [name for name in names if name not in existing]
    if missing:
        raise SystemExit(f'Missing signals in {asset}: {missing}')
print('CONFIG_OK')
print('storage.enabled =', c.storage.enabled)
print('storage.telemetry_history_enabled =', c.storage.telemetry_history_enabled)
print('fast_bess_logger.enabled =', c.fast_bess_logger.enabled)
print('fast_bess_logger.interval_sec =', c.fast_bess_logger.interval_sec)
print('fast_bess_logger.profile_name =', c.fast_bess_logger.profile_name)
PY

echo "Reloading systemd and starting services..."
systemctl daemon-reload
systemctl start ems-v3-gateway.service
sleep 8
systemctl start ems-v3-soc-controller.service 2>/dev/null || true

echo "Gateway status:"
systemctl status ems-v3-gateway.service --no-pager -l || true

echo "DONE"
echo "Backup saved at: $BACKUP_DIR"
echo "Next checks:"
echo "  curl -s http://127.0.0.1:8000/api/fast-bess/status -H \"Authorization: Bearer \\$TOKEN\" | python3 -m json.tool"
echo "  curl -s http://127.0.0.1:8000/api/fast-bess/latest -H \"Authorization: Bearer \\$TOKEN\" | python3 -m json.tool"
