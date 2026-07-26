#!/bin/sh
CONFIG_FILE="/etc/ems_wifi_boot.conf"
[ -f "$CONFIG_FILE" ] && . "$CONFIG_FILE"
WIFI_IFACE="${WIFI_IFACE:-mlan0}"
WIFI_LOG="${WIFI_LOG:-/var/log/ems_wifi_boot.log}"

echo "======================================"
echo "EMS V3 Wi-Fi Status"
echo "======================================"
printf 'Service        : %s\n' "$(systemctl is-active ems-v3-wifi.service 2>/dev/null || true)"
printf 'Enabled        : %s\n' "$(systemctl is-enabled ems-v3-wifi.service 2>/dev/null || true)"
echo
echo "[Wi-Fi link]"
iw dev "$WIFI_IFACE" link 2>/dev/null || true
echo
echo "[IP address]"
ip -br addr show "$WIFI_IFACE" 2>/dev/null || true
echo
echo "[Routes]"
ip route 2>/dev/null || true
echo
echo "[Connectivity]"
ping -c 2 -W 3 1.1.1.1 2>/dev/null || true
getent hosts google.com 2>/dev/null || true
echo
echo "[Recent boot log]"
tail -n 30 "$WIFI_LOG" 2>/dev/null || echo "No Wi-Fi boot log found"
echo "======================================"
