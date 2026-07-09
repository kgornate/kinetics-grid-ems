#!/bin/sh
# Install EMS network boot scripts on FRDM-i.MX93.
set -u

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST_DIR="/root/kinetics-grid-ems/ems_network_bootup"
CONFIG_DEST="/etc/ems_network.conf"
NB_CONFIG_DEST="/etc/nb_ems_gateway.conf"
NETWORK_SERVICE_DEST="/etc/systemd/system/ems-network-setup.service"
NB_SERVICE_DEST="/etc/systemd/system/nb-ems-gateway.service"
SOC_SOLIS_SERVICE_DEST="/etc/systemd/system/nb-ems-soc-solis-controller.service"
PROFILE_DEST="/etc/profile.d/ems_network_status.sh"

echo "======================================"
echo "Installing EMS network boot scripts"
echo "======================================"

mkdir -p "$DEST_DIR"
cp -v "$SRC_DIR/scripts/"*.sh "$DEST_DIR/"
if ls "$SRC_DIR/scripts/"*.py >/dev/null 2>&1; then
    cp -v "$SRC_DIR/scripts/"*.py "$DEST_DIR/"
fi
chmod +x "$DEST_DIR/"*.sh
chmod +x "$DEST_DIR/"*.py 2>/dev/null || true

if [ -f "$CONFIG_DEST" ]; then
    BACKUP="$CONFIG_DEST.bak.$(date +%Y%m%d_%H%M%S)"
    echo "Existing config found. Backup: $BACKUP"
    cp -v "$CONFIG_DEST" "$BACKUP"
fi
cp -v "$SRC_DIR/config/ems_network.conf" "$CONFIG_DEST"
chmod 600 "$CONFIG_DEST"

if [ -f "$NB_CONFIG_DEST" ]; then
    NB_BACKUP="$NB_CONFIG_DEST.bak.$(date +%Y%m%d_%H%M%S)"
    echo "Existing NorthBound gateway config found. Backup: $NB_BACKUP"
    cp -v "$NB_CONFIG_DEST" "$NB_BACKUP"
fi
cp -v "$SRC_DIR/config/nb_ems_gateway.conf" "$NB_CONFIG_DEST"
chmod 600 "$NB_CONFIG_DEST"

cp -v "$SRC_DIR/systemd/ems-network-setup.service" "$NETWORK_SERVICE_DEST"
cp -v "$SRC_DIR/systemd/nb-ems-gateway.service" "$NB_SERVICE_DEST"
if [ -f "$SRC_DIR/systemd/nb-ems-soc-solis-controller.service" ]; then
    cp -v "$SRC_DIR/systemd/nb-ems-soc-solis-controller.service" "$SOC_SOLIS_SERVICE_DEST"
fi
cp -v "$SRC_DIR/profile/ems_network_status.sh" "$PROFILE_DEST"
chmod +x "$PROFILE_DEST"

if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload
    systemctl enable ems-network-setup.service
    systemctl enable nb-ems-gateway.service
    # Installed but not auto-enabled by default. Enable after manual Solis+BESS validation.
    systemctl disable nb-ems-soc-solis-controller.service 2>/dev/null || true

    echo ""
    echo "Starting network setup first..."
    systemctl restart ems-network-setup.service
    systemctl status ems-network-setup.service --no-pager | head -25 || true

    echo ""
    echo "Starting NorthBound EMS Gateway after network setup..."
    systemctl restart nb-ems-gateway.service
    systemctl status nb-ems-gateway.service --no-pager | head -25 || true
else
    echo "systemctl not found; run manually: $DEST_DIR/ems_network_all_setup.sh"
    echo "Then run manually: $DEST_DIR/nb_ems_gateway_start.sh"
fi

echo ""
echo "Install done. Useful commands:"
echo "  cat /etc/ems_network.conf"
echo "  cat /var/log/ems_network_setup.log"
echo "  systemctl status ems-network-setup.service --no-pager"
echo "  systemctl status nb-ems-gateway.service --no-pager"
echo "  systemctl status nb-ems-soc-solis-controller.service --no-pager"
echo "  journalctl -u nb-ems-gateway.service -f"
echo "  journalctl -u nb-ems-soc-solis-controller.service -f"
echo "  /root/kinetics-grid-ems/ems_network_bootup/route_check.sh"
echo "======================================"
