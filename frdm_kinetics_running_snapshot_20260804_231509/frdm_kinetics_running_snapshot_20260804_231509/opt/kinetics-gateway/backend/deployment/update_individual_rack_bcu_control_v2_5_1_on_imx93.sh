#!/bin/sh
set -eu

BACKEND=/opt/kinetics-gateway/backend
SERVICE=kinetics-gateway.service
CONFIG=/etc/kinetics-gateway/config.json
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PATCH_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_ROOT=/opt/kinetics-gateway/backups/v2_5_1_individual_rack_bcu_$STAMP

if [ ! -d "$BACKEND" ]; then
  echo "ERROR: backend directory not found: $BACKEND" >&2
  exit 1
fi

FILES="
app/services/bms_pcs_control.py
FIELD_FINDINGS_MULTI_PAIR_V2_5_1.md
CHANGELOG_V2_5_1.txt
README_V2_5_1_PATCH.txt
deployment/update_individual_rack_bcu_control_v2_5_1_on_imx93.sh
"

for rel in $FILES; do
  if [ ! -f "$PATCH_ROOT/$rel" ]; then
    echo "ERROR: release file missing: $PATCH_ROOT/$rel" >&2
    exit 1
  fi
done

mkdir -p "$BACKUP_ROOT"
for rel in $FILES; do
  if [ -e "$BACKEND/$rel" ]; then
    mkdir -p "$BACKUP_ROOT/$(dirname "$rel")"
    cp -a "$BACKEND/$rel" "$BACKUP_ROOT/$rel"
  fi
done
if [ -f "$CONFIG" ]; then
  mkdir -p "$BACKUP_ROOT/etc"
  cp -a "$CONFIG" "$BACKUP_ROOT/etc/config.json"
fi

echo "Stopping $SERVICE..."
systemctl stop "$SERVICE"

for rel in $FILES; do
  mkdir -p "$BACKEND/$(dirname "$rel")"
  install -m 0644 "$PATCH_ROOT/$rel" "$BACKEND/$rel"
done
chmod 0755 "$BACKEND/deployment/update_individual_rack_bcu_control_v2_5_1_on_imx93.sh"

rm -rf "$BACKEND/app/services/__pycache__"

PYTHON=/opt/kinetics-gateway/venv/bin/python
if [ ! -x "$PYTHON" ]; then
  PYTHON=python3
fi

cd "$BACKEND"
"$PYTHON" -m py_compile app/services/bms_pcs_control.py

echo "Restarting $SERVICE..."
systemctl restart "$SERVICE"
sleep 10
systemctl --no-pager --full status "$SERVICE" | sed -n '1,30p'

echo
echo "Checking V2.5.1 capabilities..."
"$PYTHON" "$BACKEND/tools/control_sequence_cli.py" capabilities || true

echo
echo "V2.5.1 individual-rack BCU control update installed."
echo "Backup: $BACKUP_ROOT"
echo "Active hardware configuration, automatic-enable setting and timeout values were preserved."
echo "No BMS or PCS hardware command was sent by this installer."
