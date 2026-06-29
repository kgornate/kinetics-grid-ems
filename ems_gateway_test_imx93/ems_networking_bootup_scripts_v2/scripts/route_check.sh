#!/bin/sh
CONFIG_FILE="/etc/ems_network.conf"
[ -f "$CONFIG_FILE" ] && . "$CONFIG_FILE"

echo "======================================"
echo "EMS Network Route Check"
echo "======================================"
echo "[Interfaces]"
ip -br addr show eth0 2>/dev/null || true
ip -br addr show eth1 2>/dev/null || true
ip -br addr show mlan0 2>/dev/null || true

echo ""
echo "[Default routes]"
ip route show default || true

echo ""
echo "[Cloudflare/internet route]"
ip route get 1.1.1.1 2>/dev/null || true
ip route get 8.8.8.8 2>/dev/null || true

echo ""
echo "[eth0 PC peer route]"
ip route get "${ETH0_DIRECT_PEER_IP:-192.168.10.1}" 2>/dev/null || true

echo ""
echo "[eth1 field routes]"
for TARGET in ${FIELD_TARGET_IPS:-192.168.1.100 192.168.1.200}; do
    ip route get "$TARGET" 2>/dev/null || true
done

echo ""
echo "[Cloudflared]"
systemctl is-active cloudflared 2>/dev/null || true
ps aux | grep cloudflared | grep -v grep || true

echo "======================================"
