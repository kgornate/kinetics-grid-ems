#!/bin/sh

# ==========================================================
# EMS Gateway Full Network Setup
#
# eth0  = PC / Flutter dashboard side
# eth1  = Real PCS Modbus TCP side
# mlan0 = Wi-Fi / internet side
#
# This master script calls individual setup scripts and logs output.
# ==========================================================

LOG_FILE="/var/log/ems_network_setup.log"
WORKDIR="/root/kinetics-grid-ems/ems_gateway_test_imx93"

ETH0_SCRIPT="$WORKDIR/imx93_eth_setup.sh"
ETH1_SCRIPT="$WORKDIR/imx93_eth1_pcs_setup.sh"
WIFI_SCRIPT="$WORKDIR/imx93_wifi_setup.sh"

echo "======================================" | tee "$LOG_FILE"
echo "EMS Gateway Full Network Setup" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "======================================" | tee -a "$LOG_FILE"

cd "$WORKDIR"

echo "" | tee -a "$LOG_FILE"
echo "[1] Running eth0 PC/Dashboard setup..." | tee -a "$LOG_FILE"
if [ -x "$ETH0_SCRIPT" ]; then
    "$ETH0_SCRIPT" 2>&1 | tee -a "$LOG_FILE"
    ETH0_RESULT=$?
else
    echo "ERROR: $ETH0_SCRIPT not found or not executable" | tee -a "$LOG_FILE"
    ETH0_RESULT=1
fi

echo "" | tee -a "$LOG_FILE"
echo "[2] Running eth1 PCS setup..." | tee -a "$LOG_FILE"
if [ -x "$ETH1_SCRIPT" ]; then
    "$ETH1_SCRIPT" 2>&1 | tee -a "$LOG_FILE"
    ETH1_RESULT=$?
else
    echo "ERROR: $ETH1_SCRIPT not found or not executable" | tee -a "$LOG_FILE"
    ETH1_RESULT=1
fi

echo "" | tee -a "$LOG_FILE"
echo "[3] Running Wi-Fi setup..." | tee -a "$LOG_FILE"
if [ -x "$WIFI_SCRIPT" ]; then
    "$WIFI_SCRIPT" 2>&1 | tee -a "$LOG_FILE"
    WIFI_RESULT=$?
else
    echo "ERROR: $WIFI_SCRIPT not found or not executable" | tee -a "$LOG_FILE"
    WIFI_RESULT=1
fi

echo "" | tee -a "$LOG_FILE"
echo "[4] Final interface status:" | tee -a "$LOG_FILE"
ip -br addr show eth0 2>&1 | tee -a "$LOG_FILE" || true
ip -br addr show eth1 2>&1 | tee -a "$LOG_FILE" || true
ip -br addr show mlan0 2>&1 | tee -a "$LOG_FILE" || true

echo "" | tee -a "$LOG_FILE"
echo "[5] Final route status:" | tee -a "$LOG_FILE"
ip route get 192.168.10.1 2>&1 | tee -a "$LOG_FILE" || true
ip route get 192.168.1.200 2>&1 | tee -a "$LOG_FILE" || true
ip route get 8.8.8.8 2>&1 | tee -a "$LOG_FILE" || true

echo "" | tee -a "$LOG_FILE"
echo "[6] Ping checks:" | tee -a "$LOG_FILE"

echo "PC side eth0 -> 192.168.10.1" | tee -a "$LOG_FILE"
ping -I eth0 -c 2 -W 2 192.168.10.1 2>&1 | tee -a "$LOG_FILE" || true

echo "PCS side eth1 -> 192.168.1.200" | tee -a "$LOG_FILE"
ping -I eth1 -c 2 -W 2 192.168.1.200 2>&1 | tee -a "$LOG_FILE" || true

echo "Wi-Fi mlan0 -> google.com" | tee -a "$LOG_FILE"
ping -I mlan0 -c 2 -W 3 google.com 2>&1 | tee -a "$LOG_FILE" || true

echo "" | tee -a "$LOG_FILE"
echo "======================================" | tee -a "$LOG_FILE"
echo "EMS Network Setup Summary" | tee -a "$LOG_FILE"
echo "eth0 setup result : $ETH0_RESULT" | tee -a "$LOG_FILE"
echo "eth1 setup result : $ETH1_RESULT" | tee -a "$LOG_FILE"
echo "wifi setup result : $WIFI_RESULT" | tee -a "$LOG_FILE"
echo "Log file          : $LOG_FILE" | tee -a "$LOG_FILE"
echo "======================================" | tee -a "$LOG_FILE"

if [ "$ETH0_RESULT" -ne 0 ] || [ "$ETH1_RESULT" -ne 0 ] || [ "$WIFI_RESULT" -ne 0 ]; then
    echo "ERROR: One or more network setup steps failed." | tee -a "$LOG_FILE"
    exit 1
fi

echo "EMS full network setup completed successfully." | tee -a "$LOG_FILE"
exit 0
EOF

chmod +x ems_network_all_setup.sh