#!/bin/sh
set -eu

BACKUP=${1:-}
CONFIRMATION=${2:-}
REQUIRED_CONFIRMATION="ROLLBACK_MULTI_PAIR_V2_6"
TARGET="/opt/kinetics-gateway/backend"
CONFIG="/etc/kinetics-gateway/config.json"
SERVICE="kinetics-gateway.service"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Run this rollback as root."
    exit 1
fi

if [ -z "$BACKUP" ] || [ ! -d "$BACKUP" ]; then
    echo "Usage: sh $0 /root/kinetics_multi_pair_v2_6_backup_TIMESTAMP $REQUIRED_CONFIRMATION"
    exit 2
fi

if [ "$CONFIRMATION" != "$REQUIRED_CONFIRMATION" ]; then
    echo "No files changed."
    echo "Confirm all four pairs are safely stopped at 0 kW, then run:"
    echo "  sh $0 $BACKUP $REQUIRED_CONFIRMATION"
    exit 2
fi

for FILE in \
    app/services/bms_pcs_control.py \
    app/core/config.py \
    app/api/routes.py \
    app/main.py \
    config.json
 do
    if [ ! -f "$BACKUP/$FILE" ]; then
        echo "ERROR: Backup file missing: $BACKUP/$FILE"
        exit 1
    fi
 done

systemctl stop "$SERVICE"
cp -a "$BACKUP/app/services/bms_pcs_control.py" "$TARGET/app/services/"
cp -a "$BACKUP/app/core/config.py" "$TARGET/app/core/"
cp -a "$BACKUP/app/api/routes.py" "$TARGET/app/api/"
cp -a "$BACKUP/app/main.py" "$TARGET/app/"
cp -a "$BACKUP/config.json" "$CONFIG"
if [ -d "$BACKUP/tests" ]; then
    mkdir -p "$TARGET/tests"
    cp -a "$BACKUP/tests/." "$TARGET/tests/"
fi

PYTHON="$TARGET/../venv/bin/python3"
if [ ! -x "$PYTHON" ]; then
    PYTHON=python3
fi
"$PYTHON" -m py_compile \
    "$TARGET/app/services/bms_pcs_control.py" \
    "$TARGET/app/core/config.py" \
    "$TARGET/app/api/routes.py" \
    "$TARGET/app/main.py"

systemctl start "$SERVICE"
sleep 8
systemctl is-active --quiet "$SERVICE"

echo "Rollback completed from: $BACKUP"
echo "No BMS or PCS hardware command was sent by this rollback."
systemctl status "$SERVICE" --no-pager -l | sed -n '1,24p'
