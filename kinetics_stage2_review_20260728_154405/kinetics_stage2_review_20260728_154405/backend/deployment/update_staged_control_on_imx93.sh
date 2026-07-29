#!/bin/sh
set -eu

PATCH_ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
TARGET=/opt/kinetics-gateway/backend
VENV=/opt/kinetics-gateway/venv
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP=/root/kinetics_staged_control_backup_${STAMP}

if [ ! -d "$TARGET" ]; then
  echo "Target backend not found: $TARGET" >&2
  exit 1
fi
if [ ! -x "$VENV/bin/python" ]; then
  echo "Gateway virtual environment not found: $VENV" >&2
  exit 1
fi

FILES="
app/core/config.py
app/assets/bms_driver.py
app/assets/pcs_driver.py
app/services/bms_pcs_control.py
app/services/gateway_service.py
app/api/routes.py
app/main.py
configs/pcs_overrides.json
tools/control_sequence_cli.py
deployment/enable_staged_control_on_imx93.sh
deployment/disable_staged_control_on_imx93.sh
deployment/update_staged_control_on_imx93.sh
configs/control_sequence_pair1_template.json
STAGED_BMS_PCS_CONTROL.md
tests/test_bms_pcs_control.py
"

mkdir -p "$BACKUP"
for rel in $FILES; do
  if [ -e "$TARGET/$rel" ]; then
    mkdir -p "$BACKUP/$(dirname "$rel")"
    cp -a "$TARGET/$rel" "$BACKUP/$rel"
  fi
done
if [ -d "$TARGET/protocol_sources/control_logic" ]; then
  mkdir -p "$BACKUP/protocol_sources"
  cp -a "$TARGET/protocol_sources/control_logic" "$BACKUP/protocol_sources/"
fi

systemctl stop kinetics-gateway.service

for rel in $FILES; do
  mkdir -p "$TARGET/$(dirname "$rel")"
  cp -a "$PATCH_ROOT/$rel" "$TARGET/$rel"
done
mkdir -p "$TARGET/protocol_sources"
rm -rf "$TARGET/protocol_sources/control_logic"
cp -a "$PATCH_ROOT/protocol_sources/control_logic" "$TARGET/protocol_sources/"
chmod +x \
  "$TARGET/tools/control_sequence_cli.py" \
  "$TARGET/deployment/enable_staged_control_on_imx93.sh" \
  "$TARGET/deployment/disable_staged_control_on_imx93.sh" \
  "$TARGET/deployment/update_staged_control_on_imx93.sh"

cd "$TARGET"
"$VENV/bin/python" -m compileall -q app tools
KINETICS_CONFIG=/etc/kinetics-gateway/config.json "$VENV/bin/python" - <<'PY'
from app.core.config import load_config
c=load_config()
print('Active config preserved and valid')
print('Mode:', c.mode)
print('BMS:', c.bms.host, c.bms.connection_mode, [(r.rack_id,r.port,r.unit_id) for r in c.bms.racks])
print('PCS:', c.pcs.transport, c.pcs.serial.device, c.pcs.serial.baudrate, [(d.asset_id,d.unit_id,d.enabled) for d in c.pcs.devices])
print('Control sequence enabled:', c.control_sequence.enabled)
print('Full automatic sequence allowed:', c.control_sequence.allow_full_automatic_sequence)
PY

systemctl start kinetics-gateway.service
sleep 6
systemctl status kinetics-gateway.service --no-pager -l

echo "Update complete."
echo "Backup: $BACKUP"
echo "Active /etc config, BMS catalog, network files and systemd units were not replaced."
echo "No hardware write was enabled or executed."
echo "Next: sh $TARGET/deployment/enable_staged_control_on_imx93.sh ENABLE_STAGE_WRITES"
