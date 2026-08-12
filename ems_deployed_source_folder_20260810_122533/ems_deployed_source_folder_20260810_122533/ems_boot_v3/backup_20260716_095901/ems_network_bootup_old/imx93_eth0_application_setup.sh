#!/bin/sh
# ==========================================================
# i.MX93 eth0 Application-Side Setup
# eth0 can be either:
#   - direct PC/Flutter link with static 192.168.10.2/24
#   - LAN/router DHCP link for internet
#   - auto: DHCP first, then static fallback
# ==========================================================

set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/ems_common.sh"
load_config

IFACE="$ETH0_IFACE"
MODE="$ETH0_MODE"

cat <<EOM
======================================
i.MX93 eth0 Application-Side Setup
======================================
Interface : $IFACE
Mode      : $MODE
Static IP : $ETH0_DIRECT_IP
Peer PC   : $ETH0_DIRECT_PEER_IP
Metric    : $ETH0_METRIC
======================================
EOM

if ! ip link show "$IFACE" >/dev/null 2>&1; then
    echo "ERROR: Interface $IFACE not found"
    exit 1
fi

kill_udhcpc_for_iface() {
    pkill -f "udhcpc.*-i $IFACE" 2>/dev/null || true
}

setup_direct_pc() {
    echo "[eth0] Configuring direct PC/static mode..."
    kill_udhcpc_for_iface
    ip link set "$IFACE" up
    ip addr flush dev "$IFACE" 2>/dev/null || true
    ip addr add "$ETH0_DIRECT_IP" dev "$IFACE"
    ip route del default dev "$IFACE" 2>/dev/null || true
    echo "[eth0] Direct PC/static mode ready."
}

setup_lan_dhcp() {
    echo "[eth0] Configuring LAN DHCP mode..."
    ip link set "$IFACE" up
    ip addr flush dev "$IFACE" 2>/dev/null || true
    kill_udhcpc_for_iface
    if udhcpc -i "$IFACE" -q -n -T 3 -t 3; then
        set_default_metric_if_present "$IFACE" "$ETH0_METRIC"
        echo "[eth0] DHCP success."
        return 0
    fi
    echo "[eth0] DHCP failed."
    return 1
}

case "$MODE" in
    direct_pc)
        setup_direct_pc
        ;;
    lan_dhcp)
        setup_lan_dhcp || exit 1
        ;;
    auto)
        if setup_lan_dhcp; then
            echo "[eth0] Auto mode selected LAN DHCP."
        else
            echo "[eth0] Auto mode falling back to direct PC/static."
            setup_direct_pc
        fi
        ;;
    *)
        echo "ERROR: Invalid ETH0_MODE=$MODE. Use direct_pc, lan_dhcp, or auto."
        exit 1
        ;;
esac

echo ""
echo "[eth0] Address:"
ip -br addr show "$IFACE" || true

echo "[eth0] Carrier: $(has_carrier "$IFACE")"

echo "[eth0] Route to direct PC peer:"
ip route get "$ETH0_DIRECT_PEER_IP" 2>/dev/null || true

echo "======================================"
echo "eth0 application-side setup completed"
echo "======================================"
