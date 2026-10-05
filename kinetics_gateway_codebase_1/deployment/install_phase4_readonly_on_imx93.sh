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
  cp "$INSTALL_ROOT/backend/configs/elecod_lineage_4pair_phase4_readonly_template.json" "$CONFIG_ROOT/config.json"
  echo "Created $CONFIG_ROOT/config.json. EDIT BMS/PCS IP/port/Unit-ID values before starting the service." >&2
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

echo "Phase-4 code installed but service was NOT started automatically."
echo "1) Edit $CONFIG_ROOT/config.json"
echo "2) Run the read-only commissioning probe"
echo "3) Start with: systemctl start ornate-ems-gateway.service"
