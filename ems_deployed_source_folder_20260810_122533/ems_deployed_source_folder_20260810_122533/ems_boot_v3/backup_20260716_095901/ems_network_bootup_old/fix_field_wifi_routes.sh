#!/bin/sh

echo "[route-fix] Forcing eth1 as field-only and mlan0 as internet"

pkill -f "udhcpc.*eth1" 2>/dev/null || true
pkill -f "udhcpc.*eth0" 2>/dev/null || true

ip route del default dev eth1 2>/dev/null || true
ip route del default via 192.168.100.1 dev eth1 2>/dev/null || true
ip route del default dev eth0 2>/dev/null || true
ip route del default via 192.168.100.1 dev eth0 2>/dev/null || true

ip addr flush dev eth0 2>/dev/null || true
ip link set eth0 down 2>/dev/null || true

ip addr flush dev eth1 2>/dev/null || true
ip addr add 192.168.100.2/24 dev eth1 2>/dev/null || true
ip link set eth1 up 2>/dev/null || true

ip route replace 192.168.100.151 dev eth1 src 192.168.100.2 2>/dev/null || true
ip route replace 192.168.100.153 dev eth1 src 192.168.100.2 2>/dev/null || true

if ip -4 addr show mlan0 | grep -q "inet "; then
    ip route replace default via 192.168.1.1 dev mlan0 metric 10 2>/dev/null || true
fi

ip route flush cache 2>/dev/null || true

ip -br addr
ip route
ip route get 8.8.8.8 || true
