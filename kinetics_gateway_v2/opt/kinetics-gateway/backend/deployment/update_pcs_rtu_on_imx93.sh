#!/bin/sh
set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
INSTALL_ROOT=/opt/kinetics-gateway
BACKEND_ROOT=$INSTALL_ROOT/backend
VENV=$INSTALL_ROOT/venv
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_ROOT=/root/kinetics_pcs_rtu_update_backup_$STAMP

if [ ! -x "$VENV/bin/python" ]; then
  echo "Existing Kinetics virtual environment not found at $VENV" >&2
  exit 1
fi
if [ ! -d "$BACKEND_ROOT/app" ]; then
  echo "Existing Kinetics backend not found at $BACKEND_ROOT" >&2
  exit 1
fi

mkdir -p "$BACKUP_ROOT"
for item in \
  app/core/config.py \
  app/assets/pcs_driver.py \
  app/protocols/modbus_rtu.py \
  app/services/gateway_service.py \
  app/api/routes.py \
  app/main.py \
  requirements.txt; do
  if [ -f "$BACKEND_ROOT/$item" ]; then
    mkdir -p "$BACKUP_ROOT/$(dirname "$item")"
    cp -p "$BACKEND_ROOT/$item" "$BACKUP_ROOT/$item"
  fi
done

systemctl stop kinetics-gateway.service

# Install only the new serial dependency. Existing application dependencies,
# /etc/kinetics-gateway configuration, network files and systemd units are untouched.
"$VENV/bin/pip" install 'pyserial>=3.5,<4'

for item in \
  app/core/config.py \
  app/assets/pcs_driver.py \
  app/protocols/modbus_rtu.py \
  app/services/gateway_service.py \
  app/api/routes.py \
  app/main.py \
  tools/pcs_rtu_probe.py \
  tools/hardware_read_validation.py \
  requirements.txt \
  PCS_RTU_INTEGRATION.md; do
  mkdir -p "$BACKEND_ROOT/$(dirname "$item")"
  cp -p "$SOURCE_DIR/$item" "$BACKEND_ROOT/$item"
done

mkdir -p "$BACKEND_ROOT/configs" "$BACKEND_ROOT/deployment/udev"
cp -p "$SOURCE_DIR/configs/kinetics_hardware_bms_4pcs_rtu_template.json" "$BACKEND_ROOT/configs/"
cp -p "$SOURCE_DIR/deployment/udev/99-pcs-rs485.rules.example" "$BACKEND_ROOT/deployment/udev/"

cd "$BACKEND_ROOT"
"$VENV/bin/python" -m py_compile \
  app/core/config.py \
  app/assets/pcs_driver.py \
  app/protocols/modbus_rtu.py \
  app/services/gateway_service.py \
  app/api/routes.py \
  app/main.py

# Validate the currently running configuration without replacing it.
KINETICS_CONFIG=/etc/kinetics-gateway/config.json \
  "$VENV/bin/python" - <<'PY'
from app.core.config import load_config
config = load_config('/etc/kinetics-gateway/config.json')
print('Current config preserved and valid')
print('BMS:', config.bms.host, config.bms.connection_mode, len(config.bms.racks), 'racks')
print('PCS enabled:', config.pcs.enabled)
print('PCS transport:', config.pcs.transport)
print('PCS configured devices:', [(d.asset_id, d.unit_id) for d in config.pcs.devices])
PY

systemctl start kinetics-gateway.service
sleep 5
systemctl --no-pager --full status kinetics-gateway.service || true

echo "Update complete. Backup: $BACKUP_ROOT"
echo "No /etc/kinetics-gateway files, network scripts or systemd units were replaced."
