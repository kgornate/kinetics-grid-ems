#!/bin/sh
# Install EMS network boot scripts on FRDM-i.MX93.
set -u

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST_DIR="/root/kinetics-grid-ems/ems_network_bootup"
CONFIG_DEST="/etc/ems_network.conf"
SERVICE_DEST="/etc/systemd/system/ems-network-setup.service"
PROFILE_DEST="/etc/profile.d/ems_network_status.sh"

echo "======================================"
echo "Installing EMS network boot scripts"
echo "======================================"

mkdir -p "$DEST_DIR"
cp -v "$SRC_DIR/scripts/"*.sh "$DEST_DIR/"
chmod +x "$DEST_DIR/"*.sh

if [ -f "$CONFIG_DEST" ]; then
    BACKUP="$CONFIG_DEST.bak.$(date +%Y%m%d_%H%M%S)"
    echo "Existing config found. Backup: $BACKUP"
    cp -v "$CONFIG_DEST" "$BACKUP"
fi
cp -v "$SRC_DIR/config/ems_network.conf" "$CONFIG_DEST"
chmod 600 "$CONFIG_DEST"

cp -v "$SRC_DIR/systemd/ems-network-setup.service" "$SERVICE_DEST"
cp -v "$SRC_DIR/profile/ems_network_status.sh" "$PROFILE_DEST"
chmod +x "$PROFILE_DEST"

if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload
    systemctl enable ems-network-setup.service
    systemctl restart ems-network-setup.service
    systemctl status ems-network-setup.service --no-pager | head -25 || true
else
    echo "systemctl not found; run manually: $DEST_DIR/ems_network_all_setup.sh"
fi

echo ""
echo "Install done. Useful commands:"
echo "  cat /etc/ems_network.conf"
echo "  cat /var/log/ems_network_setup.log"
echo "  systemctl status ems-network-setup.service --no-pager"
echo "  /root/kinetics-grid-ems/ems_network_bootup/route_check.sh"
echo "======================================"
