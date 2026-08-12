#!/bin/sh
set -eu

. /etc/ems_boot_v3.conf

IFACE="$ETH1_IFACE"
ADDR_CIDR="$ETH1_ADDR"
IP_ONLY="${ADDR_CIDR%/*}"

echo "======================================"
echo "EMS Boot V3 - eth1 field-side setup"
echo "======================================"
echo "Interface : $IFACE"
echo "Address   : $ADDR_CIDR"
echo "Targets   : $FIELD_TARGET_1 $FIELD_TARGET_2"
echo "======================================"

pkill -f "udhcpc.*$IFACE" 2>/dev/null || true
pkill -f "dhclient.*$IFACE" 2>/dev/null || true

ip route del default dev "$IFACE" 2>/dev/null || true
ip route del default via 192.168.100.1 dev "$IFACE" 2>/dev/null || true

ip addr flush dev "$IFACE" 2>/dev/null || true
ip link set "$IFACE" up 2>/dev/null || true
ip addr add "$ADDR_CIDR" dev "$IFACE"

ip route replace "$FIELD_TARGET_1" dev "$IFACE" src "$IP_ONLY"
ip route replace "$FIELD_TARGET_2" dev "$IFACE" src "$IP_ONLY"

echo "[eth1] final status"
ip -br addr show "$IFACE"
ip route | grep -E 'default|192\.168\.100\.' || true
echo "======================================"
