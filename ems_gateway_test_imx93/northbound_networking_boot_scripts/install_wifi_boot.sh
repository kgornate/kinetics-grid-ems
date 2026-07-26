#!/bin/sh
set -eu

HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root: bash install_wifi_boot.sh"
    exit 1
fi

echo "Installing EMS V3 Wi-Fi boot files..."

mkdir -p /root/northbound-ems/ems_boot_v3/scripts
install -m 600 "$HERE/etc/ems_wifi_boot.conf" /etc/ems_wifi_boot.conf
install -m 755 "$HERE/root/northbound-ems/ems_boot_v3/scripts/imx93_wifi_v3.sh" \
    /root/northbound-ems/ems_boot_v3/scripts/imx93_wifi_v3.sh
install -m 755 "$HERE/root/northbound-ems/ems_boot_v3/scripts/ems_v3_wifi_status.sh" \
    /root/northbound-ems/ems_boot_v3/scripts/ems_v3_wifi_status.sh
install -m 644 "$HERE/etc/systemd/system/ems-v3-wifi.service" \
    /etc/systemd/system/ems-v3-wifi.service

# The custom Wi-Fi service owns mlan0.
systemctl disable connman.service 2>/dev/null || true
systemctl disable wpa_supplicant.service 2>/dev/null || true
systemctl stop connman.service 2>/dev/null || true
systemctl stop wpa_supplicant.service 2>/dev/null || true

systemctl daemon-reload
systemctl enable ems-v3-wifi.service
systemctl restart ems-v3-wifi.service

echo
echo "Current service state:"
systemctl --no-pager --full status ems-v3-wifi.service || true

echo
echo "Run this for a compact status report:"
echo "/root/northbound-ems/ems_boot_v3/scripts/ems_v3_wifi_status.sh"
echo
echo "After verification, reboot once: reboot"
