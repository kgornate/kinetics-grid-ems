#!/bin/sh

# ==========================================================
# EMS Gateway Full Network Setup
#
# eth0  = PC / Flutter dashboard side
# eth1  = Real PCS Modbus TCP side
# mlan0 = Wi-Fi / internet side
#
# Important:
#   We run eth0/eth1 once first, then Wi-Fi,
#   then re-run eth0/eth1 again after Wi-Fi DHCP.
#   This prevents Wi-Fi DHCP/ConnMan from breaking EMS routes.
# ==========================================================

LOG_FILE="/var/log/ems_network_setup.log"
WORKDIR="/root/kinetics-grid-ems/ems_gateway_test_imx93"

ETH0_SCRIPT="$WORKDIR/imx93_eth_setup.sh"
ETH1_SCRIPT="$WORKDIR/imx93_eth1_pcs_setup.sh"
WIFI_SCRIPT="$WORKDIR/imx93_wifi_setup.sh"

PC_IP="192.168.10.1"
PCS_IP="192.168.1.200"
DNS_IP="8.8.8.8"

echo "======================================" | tee "$LOG_FILE"
echo "EMS Gateway Full Network Setup" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "======================================" | tee -a "$LOG_FILE"

cd "$WORKDIR"

run_script() {
    NAME="$1"
    SCRIPT="$2"

    echo "" | tee -a "$LOG_FILE"
    echo "[$NAME] Running $SCRIPT..." | tee -a "$LOG_FILE"

    if [ -x "$SCRIPT" ]; then
        "$SCRIPT" 2>&1 | tee -a "$LOG_FILE"
        RESULT=${PIPESTATUS:-0}
        return 0
    else
        echo "ERROR: $SCRIPT not found or not executable" | tee -a "$LOG_FILE"
        return 1
    fi
}

echo "" | tee -a "$LOG_FILE"
echo "[1] Initial eth0 PC/Dashboard setup..." | tee -a "$LOG_FILE"
"$ETH0_SCRIPT" 2>&1 | tee -a "$LOG_FILE" || ETH0_RESULT=1
ETH0_RESULT=${ETH0_RESULT:-0}

echo "" | tee -a "$LOG_FILE"
echo "[2] Initial eth1 PCS setup..." | tee -a "$LOG_FILE"
"$ETH1_SCRIPT" 2>&1 | tee -a "$LOG_FILE" || ETH1_RESULT=1
ETH1_RESULT=${ETH1_RESULT:-0}

echo "" | tee -a "$LOG_FILE"
echo "[3] Wi-Fi setup..." | tee -a "$LOG_FILE"
"$WIFI_SCRIPT" 2>&1 | tee -a "$LOG_FILE" || WIFI_RESULT=1
WIFI_RESULT=${WIFI_RESULT:-0}

echo "" | tee -a "$LOG_FILE"
echo "[4] Re-applying eth0 and eth1 after Wi-Fi DHCP..." | tee -a "$LOG_FILE"

"$ETH0_SCRIPT" 2>&1 | tee -a "$LOG_FILE" || ETH0_FINAL_RESULT=1
ETH0_FINAL_RESULT=${ETH0_FINAL_RESULT:-0}

"$ETH1_SCRIPT" 2>&1 | tee -a "$LOG_FILE" || ETH1_FINAL_RESULT=1
ETH1_FINAL_RESULT=${ETH1_FINAL_RESULT:-0}

echo "" | tee -a "$LOG_FILE"
echo "[5] Final interface status:" | tee -a "$LOG_FILE"
ip -br addr show eth0 2>&1 | tee -a "$LOG_FILE" || true
ip -br addr show eth1 2>&1 | tee -a "$LOG_FILE" || true
ip -br addr show mlan0 2>&1 | tee -a "$LOG_FILE" || true

echo "" | tee -a "$LOG_FILE"
echo "[6] Final route status:" | tee -a "$LOG_FILE"
ip route get "$PC_IP" 2>&1 | tee -a "$LOG_FILE" || true
ip route get "$PCS_IP" 2>&1 | tee -a "$LOG_FILE" || true
ip route get "$DNS_IP" 2>&1 | tee -a "$LOG_FILE" || true

echo "" | tee -a "$LOG_FILE"
echo "[7] Ping checks:" | tee -a "$LOG_FILE"

echo "PC side eth0 -> $PC_IP" | tee -a "$LOG_FILE"
ping -I eth0 -c 2 -W 2 "$PC_IP" 2>&1 | tee -a "$LOG_FILE" || true

echo "PCS side eth1 -> $PCS_IP" | tee -a "$LOG_FILE"
ping -I eth1 -c 2 -W 2 "$PCS_IP" 2>&1 | tee -a "$LOG_FILE" || true

echo "Wi-Fi mlan0 -> google.com" | tee -a "$LOG_FILE"
ping -I mlan0 -c 2 -W 3 google.com 2>&1 | tee -a "$LOG_FILE" || true

echo "" | tee -a "$LOG_FILE"
echo "======================================" | tee -a "$LOG_FILE"
echo "EMS Network Setup Summary" | tee -a "$LOG_FILE"
echo "eth0 initial setup result : $ETH0_RESULT" | tee -a "$LOG_FILE"
echo "eth1 initial setup result : $ETH1_RESULT" | tee -a "$LOG_FILE"
echo "wifi setup result         : $WIFI_RESULT" | tee -a "$LOG_FILE"
echo "eth0 final setup result   : $ETH0_FINAL_RESULT" | tee -a "$LOG_FILE"
echo "eth1 final setup result   : $ETH1_FINAL_RESULT" | tee -a "$LOG_FILE"
echo "Log file                  : $LOG_FILE" | tee -a "$LOG_FILE"
echo "======================================" | tee -a "$LOG_FILE"

if [ "$ETH0_FINAL_RESULT" -ne 0 ] || [ "$ETH1_FINAL_RESULT" -ne 0 ] || [ "$WIFI_RESULT" -ne 0 ]; then
    echo "ERROR: One or more network setup steps failed." | tee -a "$LOG_FILE"
    exit 1
fi

echo "EMS full network setup completed successfully." | tee -a "$LOG_FILE"
exit 0
