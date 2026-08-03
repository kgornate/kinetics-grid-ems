#!/bin/sh
set -eu

CONF=/etc/kinetics-gateway/network.conf
[ -r "$CONF" ] || { echo "Missing $CONF" >&2; exit 1; }
. "$CONF"

configure_address() {
    iface=$1
    cidr=$2
    [ -n "$iface" ] || return 0
    [ -n "$cidr" ] || return 0
    ip link set "$iface" up
    ip address replace "$cidr" dev "$iface"
}

configure_address "${FIELD_IFACE:-eth1}" "${FIELD_PRIMARY_CIDR:-10.30.4.2/24}"

for cidr in ${FIELD_SECONDARY_CIDRS:-}; do
    configure_address "${FIELD_IFACE:-eth1}" "$cidr"
done

configure_address "${PCS_IFACE:-}" "${PCS_CIDR:-}"
configure_address "${PC_IFACE:-eth0}" "${PC_CIDR:-192.168.10.2/24}"

# Do not alter the default route. Wi-Fi/cloudflared can continue using mlan0.
ip -4 address show "${FIELD_IFACE:-eth1}" || true
ip -4 address show "${PC_IFACE:-eth0}" || true
[ -z "${PCS_IFACE:-}" ] || ip -4 address show "$PCS_IFACE" || true
