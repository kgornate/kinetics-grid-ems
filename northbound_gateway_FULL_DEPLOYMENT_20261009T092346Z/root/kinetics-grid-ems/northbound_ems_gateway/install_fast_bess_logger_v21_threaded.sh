#!/bin/sh
set -e

GW_DIR="/root/kinetics-grid-ems/northbound_ems_gateway"
PATCH_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
FILES_DIR="$PATCH_DIR/files/northbound_ems_gateway"
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="/root/kinetics-grid-ems/northbound_ems_gateway_before_fast_bess_v21_${TS}"

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
  src/nb_ems_gateway/storage/fast_bess_logger.py \
  src/nb_ems_gateway/storage/sqlite_store.py
 do
  if [ -e "$GW_DIR/$f" ]; then
    mkdir -p "$BACKUP_DIR/$(dirname "$f")"
    cp -a "$GW_DIR/$f" "$BACKUP_DIR/$f"
  fi
 done

echo "Installing V2.1 threaded timing patch files..."
cp -a "$FILES_DIR/." "$GW_DIR/"

echo "Validating Python syntax and config..."
cd "$GW_DIR"
PYTHONPATH=src python3 -m py_compile \
  src/nb_ems_gateway/storage/fast_bess_logger.py \
  src/nb_ems_gateway/storage/sqlite_store.py

PYTHONPATH=src python3 - <<'PY'
from nb_ems_gateway.config.loader import load_config
c = load_config('configs/development.json')
print('CONFIG_OK')
print('fast_bess_logger.enabled =', c.fast_bess_logger.enabled)
print('fast_bess_logger.interval_sec =', c.fast_bess_logger.interval_sec)
print('fast_bess_logger.retention_days =', c.fast_bess_logger.retention_days)
print('fast_bess_logger.profile_name =', c.fast_bess_logger.profile_name)
print('fast_bess_logger.write_mode =', c.fast_bess_logger.write_mode)
print('storage.enabled =', c.storage.enabled)
print('storage.telemetry_history_enabled =', c.storage.telemetry_history_enabled)
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
echo "Next check: sh verify_fast_bess_logger_v21_threaded.sh"
