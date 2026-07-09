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

echo ""
echo "[Solis RTU serial]"
echo "enabled=${SOLIS_RTU_ENABLED:-0} configured_port=${SOLIS_RTU_PORT:-/dev/ttyUSB1} stable_link=${SOLIS_RTU_STABLE_LINK:-/dev/ems_solis_rtu} unit_id=${SOLIS_RTU_UNIT_ID:-1} baud=${SOLIS_RTU_BAUDRATE:-9600}"
ls -l ${SOLIS_RTU_PORT:-/dev/ttyUSB1} ${SOLIS_RTU_STABLE_LINK:-/dev/ems_solis_rtu} 2>/dev/null || true
if [ -e "${SOLIS_RTU_STABLE_LINK:-/dev/ems_solis_rtu}" ]; then
    stty -F "${SOLIS_RTU_STABLE_LINK:-/dev/ems_solis_rtu}" -a 2>/dev/null || true
fi
if [ -x /root/kinetics-grid-ems/ems_network_bootup/solis_rtu_modbus_check.py ]; then
    /root/kinetics-grid-ems/ems_network_bootup/solis_rtu_modbus_check.py --port "${SOLIS_RTU_STABLE_LINK:-/dev/ems_solis_rtu}" --baudrate "${SOLIS_RTU_BAUDRATE:-9600}" --unit-id "${SOLIS_RTU_UNIT_ID:-1}" --timeout "${SOLIS_RTU_TIMEOUT_SEC:-3}" 2>/dev/null || true
fi
