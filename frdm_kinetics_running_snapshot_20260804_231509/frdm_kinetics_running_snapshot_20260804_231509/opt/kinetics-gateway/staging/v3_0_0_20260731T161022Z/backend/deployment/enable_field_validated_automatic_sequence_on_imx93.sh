#!/bin/sh
set -eu

if [ "${1:-}" != "ENABLE_FIELD_VALIDATED_AUTOMATIC_SEQUENCE" ]; then
  echo "Refusing to enable automatic high-voltage sequencing."
  echo "Run only after field validation:"
  echo "  sh $0 ENABLE_FIELD_VALIDATED_AUTOMATIC_SEQUENCE"
  exit 2
fi

CONFIG=/etc/kinetics-gateway/config.json
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP="${CONFIG}.before_automatic_sequence_${STAMP}"

if [ ! -f "$CONFIG" ]; then
  echo "ERROR: active config not found: $CONFIG" >&2
  exit 1
fi

cp -a "$CONFIG" "$BACKUP"

python3 - "$CONFIG" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
config = json.loads(path.read_text())

if config.get("mode") != "control_enabled":
    raise SystemExit("Gateway mode must already be control_enabled")
if not config.get("bms", {}).get("write_enabled"):
    raise SystemExit("BMS writes must already be enabled")
pcs = config.get("pcs", {})
if not pcs.get("write_enabled"):
    raise SystemExit("PCS writes must already be enabled")
if pcs.get("transport") != "rtu":
    raise SystemExit("PCS transport must be rtu")

pairs = config.setdefault("control_sequence", {}).setdefault("pairs", [])
pair1 = next((item for item in pairs if item.get("pair_id") == "pair_1"), None)
if not pair1 or not pair1.get("enabled"):
    raise SystemExit("pair_1 must exist and be enabled")
if int(pair1.get("rack_id", 0)) != 1 or pair1.get("pcs_asset_id") != "pcs_1":
    raise SystemExit("pair_1 must map Rack 1 to pcs_1")

control = config["control_sequence"]
control["enabled"] = True
control["allow_full_automatic_sequence"] = True
control["confirmation_phrase"] = "EXECUTE_STAGE_WRITE"
control["automatic_confirmation_phrase"] = "EXECUTE_AUTOMATIC_SEQUENCE"
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
print("Field-validated automatic sequence enabled for pair_1.")
print("Positive kW = discharge; negative kW = charge.")
print("Default automatic ramp: 10 kW every 1 second.")
PY

systemctl restart kinetics-gateway.service
sleep 5
systemctl --no-pager --full status kinetics-gateway.service | sed -n '1,30p'

echo "Config backup: $BACKUP"
echo "No BMS or PCS command was sent by this script."
