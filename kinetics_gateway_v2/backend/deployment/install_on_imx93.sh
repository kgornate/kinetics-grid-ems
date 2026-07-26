#!/bin/sh
set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
INSTALL_ROOT=/opt/kinetics-gateway
CONFIG_ROOT=/etc/kinetics-gateway

mkdir -p "$INSTALL_ROOT" "$CONFIG_ROOT" /mnt/ems-logs/kinetics-gateway
rm -rf "$INSTALL_ROOT/backend"
cp -R "$SOURCE_DIR" "$INSTALL_ROOT/backend"
python3 -m venv "$INSTALL_ROOT/venv"
"$INSTALL_ROOT/venv/bin/pip" install --upgrade pip
"$INSTALL_ROOT/venv/bin/pip" install -r "$INSTALL_ROOT/backend/requirements.txt"

if [ ! -f "$CONFIG_ROOT/config.json" ]; then
  cp "$INSTALL_ROOT/backend/configs/kinetics_hardware_template.json" "$CONFIG_ROOT/config.json"
fi
if [ ! -f "$CONFIG_ROOT/kinetics-gateway.env" ]; then
  cat > "$CONFIG_ROOT/kinetics-gateway.env" <<'EOF'
KINETICS_JWT_SECRET=CHANGE_THIS_TO_A_LONG_RANDOM_SECRET
KINETICS_INTERNAL_PASSWORD=CHANGE_THIS_INTERNAL_PASSWORD
KINETICS_CUSTOMER_PASSWORD=CHANGE_THIS_CUSTOMER_PASSWORD
EOF
  chmod 600 "$CONFIG_ROOT/kinetics-gateway.env"
fi
cp "$INSTALL_ROOT/backend/deployment/kinetics-gateway.service" /etc/systemd/system/kinetics-gateway.service
cp "$INSTALL_ROOT/backend/deployment/network/kinetics-network-setup.sh" /usr/local/sbin/kinetics-network-setup.sh
chmod 755 /usr/local/sbin/kinetics-network-setup.sh
cp "$INSTALL_ROOT/backend/deployment/network/kinetics-network.service" /etc/systemd/system/kinetics-network.service
if [ ! -f "$CONFIG_ROOT/network.conf" ]; then
  cp "$INSTALL_ROOT/backend/deployment/network/shared-switch.conf" "$CONFIG_ROOT/network.conf"
fi
systemctl daemon-reload
systemctl enable kinetics-network.service kinetics-gateway.service
systemctl restart kinetics-network.service
systemctl restart kinetics-gateway.service
systemctl --no-pager status kinetics-gateway.service || true
