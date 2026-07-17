#!/bin/sh

BOOTCFG="/etc/ems_boot_v3.conf"

get_active() {
    systemctl is-active "$1" 2>/dev/null || true
}

bool_word() {
    [ "$1" = "active" ] && echo "ACTIVE" || echo "NOT ACTIVE"
}

http_code() {
    code="$(curl -s -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || true)"
    [ -n "$code" ] || code="000"
    echo "$code"
}

ETH1_STATE="$(get_active ems-v3-eth1.service)"
WIFI_STATE="$(get_active ems-v3-wifi.service)"
CF_STATE="$(get_active cloudflared.service)"
GW_STATE="$(get_active ems-v3-gateway.service)"
SOC_STATE="$(get_active ems-v3-soc-controller.service)"
SOLIS_LINK_STATE="$(get_active ems-v3-solis-link.service)"

if [ "$ETH1_STATE" = "active" ] && [ "$WIFI_STATE" = "active" ]; then
    NET_STATE="V3 ACTIVE"
else
    NET_STATE="V3 NOT ACTIVE"
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

echo
echo "======================================"
echo "EMS Gateway Network Status"
echo "======================================"
printf 'Network stack   : %s\n' "$NET_STATE"
printf 'Cloudflare      : %s\n' "$(bool_word "$CF_STATE")"
printf 'V3 Gateway      : %s\n' "$(bool_word "$GW_STATE")"
printf 'SOC controller  : %s\n' "$(bool_word "$SOC_STATE")"

echo
echo "[Interface roles]"
echo "eth1  : field-side Chinese EMS / external assets"
echo "eth0  : currently unused / old local-lab path"
echo "mlan0 : Wi-Fi internet"

echo
echo "[Interfaces]"
ip -br addr show eth0 2>/dev/null || true
ip -br addr show eth1 2>/dev/null || true
ip -br addr show mlan0 2>/dev/null || true

echo
echo "[Internet route used by Cloudflare]"
ip route get 1.1.1.1 2>/dev/null || true

echo
echo "[Field target routes]"
ip route get 192.168.100.151 2>/dev/null || true
ip route get 192.168.100.153 2>/dev/null || true

echo
echo "[Solis RTU]"
printf 'enabled=%s configured_port=%s stable_link=%s unit_id=%s baud=%s\n' \
    "$SOLIS_ENABLED" "$SOLIS_PORT" "$SOLIS_LINK" "$SOLIS_UNIT" "$SOLIS_BAUD"
ls -l /dev/ems_solis_rtu /dev/ttyUSB0 2>/dev/null || true
printf 'Solis link svc   : %s\n' "$(bool_word "$SOLIS_LINK_STATE")"

echo
echo "[Local API checks]"
printf '127.0.0.1:8000 /api/health (no token) -> HTTP %s\n' "$(http_code http://127.0.0.1:8000/api/health)"
printf '127.0.0.1:7000 /api/health (no token) -> HTTP %s\n' "$(http_code http://127.0.0.1:7000/api/health)"

echo
echo "Full network log      : cat /var/log/ems_network_setup.log"
echo "Gateway start log     : cat /var/log/nb_ems_gateway_start.log"
echo "Gateway live logs     : journalctl -u ems-v3-gateway.service -f"
echo "SOC controller logs   : journalctl -u ems-v3-soc-controller.service -f"
echo "======================================"
echo
