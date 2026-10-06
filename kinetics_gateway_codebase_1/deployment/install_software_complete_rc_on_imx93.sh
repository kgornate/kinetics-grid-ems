#!/bin/sh
set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
INSTALL_ROOT=/opt/ornate-ems-gateway
CONFIG_ROOT=/etc/ornate-ems-gateway

mkdir -p "$INSTALL_ROOT" "$CONFIG_ROOT" /mnt/ems-logs/ornate-ems-gateway
rm -rf "$INSTALL_ROOT/backend"
cp -R "$SOURCE_DIR" "$INSTALL_ROOT/backend"

if [ ! -x "$INSTALL_ROOT/venv/bin/python" ]; then
  python3 -m venv "$INSTALL_ROOT/venv"
fi
"$INSTALL_ROOT/venv/bin/pip" install --upgrade pip
"$INSTALL_ROOT/venv/bin/pip" install -r "$INSTALL_ROOT/backend/requirements.txt"

if [ ! -f "$CONFIG_ROOT/config.json" ]; then
  # This is a control-capable software tree, but the default field template is
  # positively locked: BMS/PCS writes and automatic control are all disabled.
  cp "$INSTALL_ROOT/backend/configs/elecod_lineage_4pair_control_ready_template.json" "$CONFIG_ROOT/config.json"
  echo "Created $CONFIG_ROOT/config.json with hardware writes DISABLED." >&2
fi

if [ ! -f "$CONFIG_ROOT/ornate-ems-gateway.env" ]; then
  cat > "$CONFIG_ROOT/ornate-ems-gateway.env" <<'ENVEOF'
ORNATE_EMS_JWT_SECRET=CHANGE_THIS_TO_A_LONG_RANDOM_SECRET
ORNATE_EMS_INTERNAL_PASSWORD=CHANGE_THIS_INTERNAL_PASSWORD
ORNATE_EMS_CUSTOMER_PASSWORD=CHANGE_THIS_CUSTOMER_PASSWORD
ENVEOF
  chmod 600 "$CONFIG_ROOT/ornate-ems-gateway.env"
fi

cp "$INSTALL_ROOT/backend/deployment/ornate-ems-gateway.service" /etc/systemd/system/ornate-ems-gateway.service
systemctl daemon-reload
systemctl enable ornate-ems-gateway.service

echo "Software-complete RC installed. Service was NOT started automatically."
echo "Before field commissioning:"
echo "  1) edit $CONFIG_ROOT/config.json with actual IP/port/Unit IDs"
echo "  2) keep all write/control gates disabled"
echo "  3) validate Phase-4 read-only signals and all commissioning gates"
echo "  4) only then enable hardware control under the field runbook"
