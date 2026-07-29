#!/bin/sh
set -eu

CONFIRMATION=${1:-}
REQUIRED_CONFIRMATION="APPLY_MULTI_PAIR_V2_6"
TARGET="/opt/kinetics-gateway/backend"
CONFIG="/etc/kinetics-gateway/config.json"
SERVICE="kinetics-gateway.service"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SOURCE=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP="/root/kinetics_multi_pair_v2_6_backup_$STAMP"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Run this installer as root."
    exit 1
fi

if [ "$CONFIRMATION" != "$REQUIRED_CONFIRMATION" ]; then
    echo "No files changed."
    echo "Before deployment, confirm all four pairs are safely stopped at 0 kW."
    echo "Then run:"
    echo "  sh $0 $REQUIRED_CONFIRMATION"
    exit 2
fi

for FILE in \
    app/services/bms_pcs_control.py \
    app/core/config.py \
    app/api/routes.py \
    app/main.py
 do
    if [ ! -f "$SOURCE/$FILE" ]; then
        echo "ERROR: Patch source missing: $SOURCE/$FILE"
        exit 1
    fi
 done

if [ ! -d "$TARGET" ]; then
    echo "ERROR: Gateway target does not exist: $TARGET"
    exit 1
fi

if [ ! -f "$CONFIG" ]; then
    echo "ERROR: Active config does not exist: $CONFIG"
    exit 1
fi

mkdir -p "$BACKUP/app/services" "$BACKUP/app/core" "$BACKUP/app/api" "$BACKUP/tests"
cp -a "$TARGET/app/services/bms_pcs_control.py" "$BACKUP/app/services/"
cp -a "$TARGET/app/core/config.py" "$BACKUP/app/core/"
cp -a "$TARGET/app/api/routes.py" "$BACKUP/app/api/"
cp -a "$TARGET/app/main.py" "$BACKUP/app/"
cp -a "$CONFIG" "$BACKUP/config.json"
if [ -d "$TARGET/tests" ]; then
    cp -a "$TARGET/tests/." "$BACKUP/tests/"
fi

DEPLOYMENT_COMPLETE=0

rollback()
{
    set +e
    echo "Deployment failed; restoring backup from $BACKUP"
    cp -a "$BACKUP/app/services/bms_pcs_control.py" "$TARGET/app/services/"
    cp -a "$BACKUP/app/core/config.py" "$TARGET/app/core/"
    cp -a "$BACKUP/app/api/routes.py" "$TARGET/app/api/"
    cp -a "$BACKUP/app/main.py" "$TARGET/app/"
    cp -a "$BACKUP/config.json" "$CONFIG"
    if [ -d "$BACKUP/tests" ]; then
        mkdir -p "$TARGET/tests"
        cp -a "$BACKUP/tests/." "$TARGET/tests/"
    fi
    systemctl restart "$SERVICE" || true
    set -e
}

rollback_on_exit()
{
    RC=$?
    trap - EXIT INT TERM HUP
    if [ "$DEPLOYMENT_COMPLETE" -ne 1 ]; then
        rollback
    fi
    exit "$RC"
}
trap rollback_on_exit EXIT INT TERM HUP

systemctl stop "$SERVICE"

cp -a "$SOURCE/app/services/bms_pcs_control.py" "$TARGET/app/services/"
cp -a "$SOURCE/app/core/config.py" "$TARGET/app/core/"
cp -a "$SOURCE/app/api/routes.py" "$TARGET/app/api/"
cp -a "$SOURCE/app/main.py" "$TARGET/app/"
if [ -d "$SOURCE/tests" ]; then
    mkdir -p "$TARGET/tests"
    cp -a "$SOURCE/tests/." "$TARGET/tests/"
fi

python3 - "$CONFIG" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as file:
    config = json.load(file)

control = config.setdefault("control_sequence", {})
control.setdefault("runtime_monitor_enabled", True)
control.setdefault("runtime_monitor_interval_seconds", 2.0)
control["runtime_monitor_refresh_wait_seconds"] = 10.0
control["runtime_monitor_max_unverified_seconds"] = 30.0

with open(path, "w", encoding="utf-8") as file:
    json.dump(config, file, indent=2, ensure_ascii=False)
    file.write("\n")

print({
    "runtime_monitor_enabled": control.get("runtime_monitor_enabled"),
    "runtime_monitor_interval_seconds": control.get("runtime_monitor_interval_seconds"),
    "runtime_monitor_refresh_wait_seconds": control.get("runtime_monitor_refresh_wait_seconds"),
    "runtime_monitor_max_unverified_seconds": control.get("runtime_monitor_max_unverified_seconds"),
})
PY

PYTHON="$TARGET/../venv/bin/python3"
if [ ! -x "$PYTHON" ]; then
    PYTHON=python3
fi

"$PYTHON" -m py_compile \
    "$TARGET/app/services/bms_pcs_control.py" \
    "$TARGET/app/core/config.py" \
    "$TARGET/app/api/routes.py" \
    "$TARGET/app/main.py"

if "$PYTHON" -m pytest --version >/dev/null 2>&1; then
    (cd "$TARGET" && "$PYTHON" -m pytest -q tests/test_bms_pcs_control.py)
else
    echo "pytest is not installed in the runtime environment; syntax validation passed."
fi

systemctl start "$SERVICE"
sleep 8

if ! systemctl is-active --quiet "$SERVICE"; then
    echo "ERROR: Gateway service did not become active."
    exit 1
fi

DEPLOYMENT_COMPLETE=1
trap - EXIT INT TERM HUP

echo
echo "Kinetics Gateway V2.6 multi-pair runtime patch installed."
echo "Backup: $BACKUP"
echo "No BMS or PCS hardware command was sent by this installer."
echo
echo "Key behavior:"
echo "- global_refresh_lane_busy is deferred and retried, not treated as a hardware fault"
echo "- a pair safe-stops only after the configured unverified timeout or a real safety violation"
echo "- GET /api/control-sequence/status/all provides cache-only status for all enabled pairs"
echo
echo "Service status:"
systemctl status "$SERVICE" --no-pager -l | sed -n '1,24p'
