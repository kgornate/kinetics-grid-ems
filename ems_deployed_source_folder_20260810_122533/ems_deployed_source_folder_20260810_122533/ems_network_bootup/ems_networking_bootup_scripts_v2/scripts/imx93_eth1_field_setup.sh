#!/bin/sh
# ==========================================================
# i.MX93 eth1 Field-Side Setup
# Purpose:
#   eth1 = Chinese EMS / external PCS / field device network
# Important:
#   eth1 must not become default internet route.
# ==========================================================

set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/ems_common.sh"
load_config

IFACE="$ETH1_IFACE"

cat <<EOM
======================================
i.MX93 eth1 Field-Side Setup
======================================
Interface      : $IFACE
i.MX93 eth1 IP : $ETH1_FIELD_IP
Field targets  : $FIELD_TARGET_IPS
======================================
EOM

if ! ip link show "$IFACE" >/dev/null 2>&1; then
    echo "ERROR: Interface $IFACE not found"
    exit 1
fi

ip link set "$IFACE" up
ip addr flush dev "$IFACE" 2>/dev/null || true
ip addr add "$ETH1_FIELD_IP" dev "$IFACE"

# Never allow eth1 to become internet/default route.
ip route del default dev "$IFACE" 2>/dev/null || true

# Ensure kernel has connected subnet route through eth1.
# This normally appears automatically when assigning the IP.

echo ""
echo "[eth1] Address:"
ip -br addr show "$IFACE" || true

echo "[eth1] Carrier: $(has_carrier "$IFACE")"

echo ""
echo "[eth1] Field target route checks:"
for TARGET in $FIELD_TARGET_IPS; do
    echo "Target $TARGET:"
    ip route get "$TARGET" 2>/dev/null || true
done

echo "======================================"
echo "eth1 field-side setup completed"
echo "======================================"
