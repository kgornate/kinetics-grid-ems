#!/bin/sh
set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
INSTALL_ROOT=/opt/kinetics-gateway
BACKEND_ROOT=$INSTALL_ROOT/backend
VENV=$INSTALL_ROOT/venv
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_ROOT=/root/kinetics_pcs_hmi_map_backup_$STAMP

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
  generated_protocols/pcs_catalog.json \
  configs/kinetics_hardware_bms_4pcs_rtu_template.json \
  configs/kinetics_hardware_bms_pcs1_rtu_readonly_template.json \
  tools/pcs_rtu_probe.py \
  tools/extract_pcs_hmi_catalog.py \
  requirements.txt; do
  if [ -f "$BACKEND_ROOT/$item" ]; then
    mkdir -p "$BACKUP_ROOT/$(dirname "$item")"
    cp -p "$BACKEND_ROOT/$item" "$BACKUP_ROOT/$item"
  fi
done

systemctl stop kinetics-gateway.service

"$VENV/bin/pip" install 'pyserial>=3.5,<4'

for item in \
  app/core/config.py \
  app/assets/pcs_driver.py \
  app/protocols/modbus_rtu.py \
  app/services/gateway_service.py \
  app/api/routes.py \
  app/main.py \
  generated_protocols/pcs_catalog.json \
  configs/kinetics_hardware_bms_4pcs_rtu_template.json \
  configs/kinetics_hardware_bms_pcs1_rtu_readonly_template.json \
  tools/pcs_rtu_probe.py \
  tools/extract_pcs_hmi_catalog.py \
  tools/hardware_read_validation.py \
  requirements.txt \
  PCS_RTU_INTEGRATION.md \
  PCS_RTU_HMI_MAP_VALIDATION.md; do
  mkdir -p "$BACKEND_ROOT/$(dirname "$item")"
  cp -p "$SOURCE_DIR/$item" "$BACKEND_ROOT/$item"
done

mkdir -p "$BACKEND_ROOT/protocol_sources/pcs_hmi" "$BACKEND_ROOT/deployment/udev"
cp -p "$SOURCE_DIR"/protocol_sources/pcs_hmi/* "$BACKEND_ROOT/protocol_sources/pcs_hmi/"
cp -p "$SOURCE_DIR/deployment/udev/99-pcs-rs485.rules.example" "$BACKEND_ROOT/deployment/udev/"
cp -p "$SOURCE_DIR/deployment/enable_pcs1_readonly_on_imx93.sh" "$BACKEND_ROOT/deployment/"
cp -p "$SOURCE_DIR/deployment/disable_pcs_polling_on_imx93.sh" "$BACKEND_ROOT/deployment/"
chmod +x "$BACKEND_ROOT/deployment/enable_pcs1_readonly_on_imx93.sh" "$BACKEND_ROOT/deployment/disable_pcs_polling_on_imx93.sh"

cd "$BACKEND_ROOT"
"$VENV/bin/python" -m py_compile \
  app/core/config.py \
  app/assets/pcs_driver.py \
  app/protocols/modbus_rtu.py \
  app/services/gateway_service.py \
  app/api/routes.py \
  app/main.py \
  tools/extract_pcs_hmi_catalog.py

KINETICS_CONFIG=/etc/kinetics-gateway/config.json "$VENV/bin/python" - <<'PY'
from app.core.catalog import ProtocolCatalog
from app.core.config import load_config
config = load_config('/etc/kinetics-gateway/config.json')
catalog = ProtocolCatalog.load('generated_protocols/pcs_catalog.json')
print('Current /etc config preserved and valid')
print('BMS:', config.bms.host, config.bms.connection_mode, len(config.bms.racks), 'racks')
print('PCS currently enabled:', config.pcs.enabled)
print('Installed PCS catalog points:', len(catalog.points))
print('PCS catalog first/last:', catalog.points[0]['address_hex'], catalog.points[-1]['address_hex'])
PY

systemctl start kinetics-gateway.service
sleep 5
systemctl --no-pager --full status kinetics-gateway.service || true

echo "PCS HMI-map update complete. Backup: $BACKUP_ROOT"
echo "The active /etc/kinetics-gateway/config.json was NOT replaced."
echo "BMS code/catalog, networking, Cloudflare and systemd units were NOT replaced."
echo "To enable only PCS1 read-only after checking /dev/ttyUSB0, run:"
echo "  $BACKEND_ROOT/deployment/enable_pcs1_readonly_on_imx93.sh"
