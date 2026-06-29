#!/bin/sh
# Show EMS network status after interactive login.
case "$-" in
    *i*) ;;
    *) return 0 2>/dev/null || exit 0 ;;
esac

CONFIG_FILE="/etc/ems_network.conf"
[ -f "$CONFIG_FILE" ] && . "$CONFIG_FILE"

echo ""
echo "======================================"
echo "EMS Gateway Network Status"
echo "======================================"

if systemctl is-active ems-network-setup.service >/dev/null 2>&1; then
    echo "Network service : ACTIVE"
else
    echo "Network service : NOT ACTIVE"
fi

if systemctl is-active cloudflared >/dev/null 2>&1; then
    echo "Cloudflare      : ACTIVE"
else
    echo "Cloudflare      : NOT ACTIVE"
fi

echo ""
echo "[Interface roles]"
echo "eth1  : field-side Chinese EMS / external PCS"
echo "eth0  : local PC/Flutter or LAN Ethernet internet"
echo "mlan0 : Wi-Fi internet"

echo ""
echo "[Interfaces]"
ip -br addr show eth0 2>/dev/null || true
ip -br addr show eth1 2>/dev/null || true
ip -br addr show mlan0 2>/dev/null || true

echo ""
echo "[Internet route used by Cloudflare]"
ip route get 1.1.1.1 2>/dev/null || true

echo ""
echo "[Field target routes]"
for TARGET in ${FIELD_TARGET_IPS:-192.168.1.100 192.168.1.200}; do
    ip route get "$TARGET" 2>/dev/null || true
done

echo ""
echo "[Local API checks]"
for PORT in ${LOCAL_API_PORT:-8000} ${LOCAL_LOGS_PORT:-7000}; do
    CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 2 "http://127.0.0.1:$PORT/api/health" 2>/dev/null || echo 000)"
    echo "127.0.0.1:$PORT /api/health -> HTTP $CODE"
done

echo ""
echo "Full network log: cat /var/log/ems_network_setup.log"
echo "======================================"
echo ""
