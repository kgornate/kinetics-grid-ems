#!/bin/sh
set -eu

LOG="/var/log/ems_v3_boot_summary.log"
TMP="/tmp/ems_v3_boot_summary.tmp"

ETH1_OK=0
WIFI_OK=0
INET_OK=0
CF_OK=0
BOOT_RESULT="FAIL"

print_out() {
    cat "$TMP" >> "$LOG"
    [ -e /dev/console ] && cat "$TMP" > /dev/console || true
    [ -e /dev/ttyLP0 ] && cat "$TMP" > /dev/ttyLP0 || true
}

mkdir -p /var/log
: > "$TMP"

sleep 8

if ping -c 2 -W 2 192.168.100.151 >/dev/null 2>&1 && ping -c 2 -W 2 192.168.100.153 >/dev/null 2>&1; then
    ETH1_OK=1
fi

if iw dev mlan0 link 2>/dev/null | grep -q "Connected to"; then
    WIFI_OK=1
fi

if ping -I mlan0 -c 2 -W 2 8.8.8.8 >/dev/null 2>&1; then
    INET_OK=1
fi

if systemctl is-active cloudflared.service >/dev/null 2>&1; then
    CF_OK=1
fi

if [ "$ETH1_OK" -eq 1 ] && [ "$WIFI_OK" -eq 1 ] && [ "$INET_OK" -eq 1 ] && [ "$CF_OK" -eq 1 ]; then
    BOOT_RESULT="PASS"
fi

{
    echo
    echo "=================================================="
    echo "EMS V3 BOOT SUMMARY"
    echo "BOOT RESULT: $BOOT_RESULT"
    echo "Timestamp : $(date)"
    echo "=================================================="
    echo
    echo "[Boot timing]"
    systemd-analyze time 2>/dev/null || true
    echo
    echo "[Health flags]"
    echo "ETH1_OK=$ETH1_OK"
    echo "WIFI_OK=$WIFI_OK"
    echo "INET_OK=$INET_OK"
    echo "CLOUDFLARED_OK=$CF_OK"
    echo
    echo "[Service status]"
    echo "ems-v3-eth1.service      : $(systemctl is-active ems-v3-eth1.service 2>/dev/null || true)"
    echo "ems-v3-wifi.service      : $(systemctl is-active ems-v3-wifi.service 2>/dev/null || true)"
    echo "cloudflared.service      : $(systemctl is-active cloudflared.service 2>/dev/null || true)"
    echo
    systemctl status ems-v3-eth1.service --no-pager -l 2>/dev/null | sed -n '1,12p' || true
    echo
    systemctl status ems-v3-wifi.service --no-pager -l 2>/dev/null | sed -n '1,14p' || true
    echo
    systemctl status cloudflared.service --no-pager -l 2>/dev/null | sed -n '1,16p' || true
    echo
    echo "[Interface status]"
    ip -br addr || true
    echo
    echo "[Routes]"
    ip route || true
    echo
    echo "[Wi-Fi link]"
    iw dev mlan0 link 2>/dev/null || true
    echo
    echo "[Field ping checks]"
    ping -c 2 -W 2 192.168.100.151 2>/dev/null || true
    ping -c 2 -W 2 192.168.100.153 2>/dev/null || true
    echo
    echo "[Internet ping check]"
    ping -I mlan0 -c 2 -W 2 8.8.8.8 2>/dev/null || true
    echo
    echo "[Cloudflared recent log]"
    journalctl -b -u cloudflared.service -n 20 --no-pager -l 2>/dev/null || true
    echo
    echo "=================================================="
    echo
} >> "$TMP"

print_out
rm -f "$TMP"
