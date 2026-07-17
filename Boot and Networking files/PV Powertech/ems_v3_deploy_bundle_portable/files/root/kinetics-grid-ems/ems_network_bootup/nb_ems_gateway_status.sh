#!/bin/sh

CFG="/etc/nb_ems_gateway.conf"
BOOTCFG="/etc/ems_boot_v3.conf"

http_code() {
    code="$(curl -s -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || true)"
    [ -n "$code" ] || code="000"
    echo "$code"
}

svc_word() {
    s="$(systemctl is-active "$1" 2>/dev/null || true)"
    [ "$s" = "active" ] && echo "ACTIVE" || echo "NOT ACTIVE"
}

NB_EMS_GATEWAY_DIR=""
NB_EMS_GATEWAY_CONFIG=""
NB_EMS_GATEWAY_MOCK=""
NB_EMS_GATEWAY_API_PORT=""
PUBLIC_API_URL=""

if [ -f "$CFG" ]; then
    . "$CFG"
fi

SOLIS_ENABLED="unknown"
SOLIS_PORT=""
SOLIS_LINK=""
SOLIS_UNIT=""
SOLIS_BAUD=""
if [ -f "$BOOTCFG" ]; then
    . "$BOOTCFG"
    SOLIS_ENABLED="${SOLIS_RTU_ENABLED:-unknown}"
    SOLIS_PORT="${SOLIS_RTU_PORT:-}"
    SOLIS_LINK="${SOLIS_RTU_LINK:-}"
    SOLIS_UNIT="${SOLIS_RTU_UNIT_ID:-}"
    SOLIS_BAUD="${SOLIS_RTU_BAUD:-}"
fi

echo "======================================"
echo "NorthBound EMS Gateway Status"
echo "======================================"
printf 'Config file       : %s\n' "$CFG"
printf 'Gateway folder    : %s\n' "$NB_EMS_GATEWAY_DIR"
printf 'Gateway config    : %s\n' "$NB_EMS_GATEWAY_CONFIG"
printf 'Mock mode         : %s\n' "$NB_EMS_GATEWAY_MOCK"
printf 'Local API port    : %s\n' "$NB_EMS_GATEWAY_API_PORT"
printf 'Public API URL    : %s\n' "$PUBLIC_API_URL"

echo
echo "[Service status]"
printf 'ems-v3-gateway.service  : %s\n' "$(svc_word ems-v3-gateway.service)"
printf 'ems-v3-eth1.service     : %s\n' "$(svc_word ems-v3-eth1.service)"
printf 'ems-v3-wifi.service     : %s\n' "$(svc_word ems-v3-wifi.service)"
printf 'cloudflared.service     : %s\n' "$(svc_word cloudflared.service)"
printf 'ems-v3-soc-controller   : %s\n' "$(svc_word ems-v3-soc-controller.service)"
printf 'ems-v3-solis-link       : %s\n' "$(svc_word ems-v3-solis-link.service)"

echo
echo "[Solis RTU]"
printf 'enabled=%s port=%s stable_link=%s unit_id=%s baud=%s\n' \
    "$SOLIS_ENABLED" "$SOLIS_PORT" "$SOLIS_LINK" "$SOLIS_UNIT" "$SOLIS_BAUD"
ls -l /dev/ems_solis_rtu /dev/ttyUSB0 2>/dev/null || true

echo
echo "[Port check]"
ss -ltnp 2>/dev/null | grep -E ':8000|:7000' || echo "No process currently listening on port 8000/7000"

echo
echo "[Local API health]"
printf 'http://127.0.0.1:8000/api/health -> HTTP %s\n' "$(http_code http://127.0.0.1:8000/api/health)"
printf 'http://127.0.0.1:7000/api/health -> HTTP %s\n' "$(http_code http://127.0.0.1:7000/api/health)"

echo
echo "[Cloudflare public API health]"
printf '%s/api/health -> HTTP %s\n' "$PUBLIC_API_URL" "$(http_code "$PUBLIC_API_URL/api/health")"

echo
echo "[Recent gateway startup wrapper log]"
if [ -f /var/log/nb_ems_gateway_start.log ]; then
    tail -n 20 /var/log/nb_ems_gateway_start.log
else
    echo "No startup wrapper log found at /var/log/nb_ems_gateway_start.log"
fi

echo
echo "[Useful live log commands]"
echo "journalctl -u ems-v3-gateway.service -f"
echo "journalctl -u ems-v3-soc-controller.service -f"
echo "journalctl -u ems-v3-gateway.service -n 100 --no-pager"
echo "cat /var/log/nb_ems_gateway_start.log"
echo "======================================"
