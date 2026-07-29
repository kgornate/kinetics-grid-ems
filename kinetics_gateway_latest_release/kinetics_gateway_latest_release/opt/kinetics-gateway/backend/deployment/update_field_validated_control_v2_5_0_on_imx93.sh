#!/bin/sh
set -eu

BACKEND=/opt/kinetics-gateway/backend
SERVICE=kinetics-gateway.service
CONFIG=/etc/kinetics-gateway/config.json
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PATCH_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_ROOT=/opt/kinetics-gateway/backups/v2_5_0_field_validated_control_$STAMP

if [ ! -d "$BACKEND" ]; then
  echo "ERROR: backend directory not found: $BACKEND" >&2
  exit 1
fi

FILES="
app/core/config.py
app/services/bms_pcs_control.py
app/api/routes.py
tools/control_sequence_cli.py
FIELD_VALIDATED_CONTROL_SEQUENCE_V2_5.md
CONTROL_SEQUENCE_API_V2_5.md
deployment/enable_field_validated_automatic_sequence_on_imx93.sh
deployment/update_field_validated_control_v2_5_0_on_imx93.sh
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
chmod 0755 \
  "$BACKEND/tools/control_sequence_cli.py" \
  "$BACKEND/deployment/enable_field_validated_automatic_sequence_on_imx93.sh" \
  "$BACKEND/deployment/update_field_validated_control_v2_5_0_on_imx93.sh"

# Add new V2.5 settings without changing the existing hardware topology,
# write gates or the current automatic-enable decision.
if [ -f "$CONFIG" ]; then
  python3 - "$CONFIG" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
config = json.loads(path.read_text())
control = config.setdefault("control_sequence", {})
control.setdefault("enabled", False)
control.setdefault("allow_full_automatic_sequence", False)
control.setdefault("confirmation_phrase", "EXECUTE_STAGE_WRITE")
control.setdefault("automatic_confirmation_phrase", "EXECUTE_AUTOMATIC_SEQUENCE")
control.setdefault("automatic_stage_timeout_seconds", 20.0)
control.setdefault("power_tracking_timeout_seconds", 15.0)
control.setdefault("safe_stop_timeout_seconds", 15.0)
control.setdefault("ready_voltage_match_tolerance_v", 75.0)
control.setdefault("power_tracking_tolerance_kw", 5.0)
control.setdefault("automatic_power_ramp_step_kw", 10.0)
control.setdefault("automatic_power_ramp_interval_seconds", 1.0)
control.setdefault("runtime_monitor_enabled", True)
control.setdefault("runtime_monitor_interval_seconds", 1.0)
control.setdefault("validation_dc_bus_threshold_v", 50.0)
path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
print("Active hardware configuration preserved and V2.5 defaults added.")
print("Automatic sequence currently allowed:", control["allow_full_automatic_sequence"])
PY
fi

rm -rf \
  "$BACKEND/app/core/__pycache__" \
  "$BACKEND/app/services/__pycache__" \
  "$BACKEND/app/api/__pycache__" \
  "$BACKEND/tools/__pycache__"

PYTHON=/opt/kinetics-gateway/venv/bin/python
if [ ! -x "$PYTHON" ]; then
  PYTHON=python3
fi

cd "$BACKEND"
"$PYTHON" -m compileall -q app tools

echo "Restarting $SERVICE..."
systemctl restart "$SERVICE"
sleep 5
systemctl --no-pager --full status "$SERVICE" | sed -n '1,30p'

echo
echo "Checking V2.5 capabilities..."
"$PYTHON" "$BACKEND/tools/control_sequence_cli.py" capabilities || true

echo
echo "V2.5.0 field-validated control update installed."
echo "Backup: $BACKUP_ROOT"
echo "No hardware command was sent by this installer."
echo "To enable automatic mode after confirming field conditions:"
echo "  sh $BACKEND/deployment/enable_field_validated_automatic_sequence_on_imx93.sh ENABLE_FIELD_VALIDATED_AUTOMATIC_SEQUENCE"
