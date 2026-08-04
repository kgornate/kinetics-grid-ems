#!/bin/sh

ensure_address()
{
    interface="$1"
    cidr="$2"

    ip link set "$interface" up 2>/dev/null || true

    if ! ip -4 addr show dev "$interface" | grep -q "inet $cidr "; then
        echo "Restoring $cidr on $interface"
        ip addr add "$cidr" dev "$interface" 2>/dev/null || \
        ip addr replace "$cidr" dev "$interface"
    fi
}

while true
do
    ensure_address eth1 192.168.111.2/24
    ensure_address eth0 192.168.10.2/24

    sleep 5
done
