#!/bin/sh

# ==========================================================
# i.MX93 EMS Gateway - eth1 PCS Network Setup
# Purpose:
#   eth0 = PC / Flutter dashboard side
#   eth1 = Real NJOY PCS Modbus TCP side
#
# PCS default IP from NJOY protocol: 192.168.1.200
# i.MX93 eth1 static IP:          192.168.1.2/24
# ==========================================================

IFACE="eth1"
IMX93_ETH1_IP="192.168.1.2/24"
PCS_IP="192.168.1.200"

echo "======================================"
echo "i.MX93 eth1 PCS Ethernet Setup"
echo "======================================"
echo "Interface       : $IFACE"
echo "i.MX93 eth1 IP  : $IMX93_ETH1_IP"
echo "PCS IP          : $PCS_IP"
echo "======================================"

echo ""
echo "[1] Checking interface..."
if ! ip link show "$IFACE" >/dev/null 2>&1; then
    echo "ERROR: Interface $IFACE not found"
    exit 1
fi

echo ""
echo "[2] Bringing $IFACE up..."
ip link set "$IFACE" up

echo ""
echo "[3] Flushing old IP addresses from $IFACE..."
ip addr flush dev "$IFACE"

echo ""
echo "[4] Assigning static PCS-side IP..."
ip addr add "$IMX93_ETH1_IP" dev "$IFACE"

echo ""
echo "[5] Removing any default route from $IFACE..."
ip route del default dev "$IFACE" 2>/dev/null || true

echo ""
echo "[6] Current eth1 address:"
ip -br addr show "$IFACE"

echo ""
echo "[7] Route check for PCS:"
ip route get "$PCS_IP" || true

echo ""
echo "[8] Link carrier status:"
if [ -f "/sys/class/net/$IFACE/carrier" ]; then
    cat "/sys/class/net/$IFACE/carrier"
else
    echo "carrier file not found"
fi

echo ""
echo "======================================"
echo "eth1 PCS Ethernet setup completed"
echo "======================================"
EOF

chmod +x imx93_eth1_pcs_setup.sh