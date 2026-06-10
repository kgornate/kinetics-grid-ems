#!/bin/sh

echo "======================================"
echo "i.MX93 Ethernet Setup"
echo "======================================"

IFACE="eth0"
IMX_IP="192.168.10.2"

echo "[1] Bringing up $IFACE..."
ip link set $IFACE up

echo "[2] Assigning static IP $IMX_IP..."
ip addr flush dev $IFACE
ip addr add $IMX_IP/24 dev $IFACE

echo "[3] Ethernet status:"
ip addr show $IFACE

echo "======================================"
echo "Ethernet setup done"
echo "======================================"

chmod +x imx93_eth_setup.sh
