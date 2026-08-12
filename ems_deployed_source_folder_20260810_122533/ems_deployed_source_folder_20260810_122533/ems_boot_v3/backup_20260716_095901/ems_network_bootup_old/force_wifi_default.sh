#!/bin/sh

echo "[force-wifi] Disabling eth0 and forcing mlan0 default route"

pkill -f "udhcpc.*eth0" 2>/dev/null || true

ip route del default via 192.168.100.1 dev eth0 metric 10 2>/dev/null || true
ip route del default via 192.168.100.1 dev eth0 metric 100 2>/dev/null || true
ip route del default dev eth0 2>/dev/null || true

ip addr flush dev eth0 2>/dev/null || true
ip link set eth0 down 2>/dev/null || true

ip link set mlan0 up 2>/dev/null || true

if ! ip -4 addr show mlan0 | grep -q "inet "; then
    ip addr add 192.168.1.103/24 dev mlan0 2>/dev/null || true
fi

ip route replace default via 192.168.1.1 dev mlan0 metric 10

echo "nameserver 192.168.1.1" > /etc/resolv.conf
echo "nameserver 8.8.8.8" >> /etc/resolv.conf
echo "nameserver 1.1.1.1" >> /etc/resolv.conf

ip -br addr show eth0
ip -br addr show mlan0
ip route
ip route get 8.8.8.8 || true
