#!/bin/sh
# ==========================================================
# EMS Gateway Full Network Setup - NorthBound/Cloudflare Mode
#
# Final roles:
#   eth1  = Chinese EMS / external PCS field network
#   eth0  = PC/Flutter direct link OR LAN Ethernet internet
#   mlan0 = Wi-Fi internet, continues like current setup
#
# Cloudflare remote monitoring:
#   The gateway only needs a working internet default route.
#   That route can be through mlan0 Wi-Fi or eth0 LAN.
# ==========================================================

set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/ems_common.sh"
load_config

ETH0_SCRIPT="$SCRIPT_DIR/imx93_eth0_application_setup.sh"
ETH1_SCRIPT="$SCRIPT_DIR/imx93_eth1_field_setup.sh"
WIFI_SCRIPT="$SCRIPT_DIR/imx93_wifi_setup.sh"

LOG_FILE="${LOG_FILE:-/var/log/ems_network_setup.log}"

mkdir -p "$(dirname "$LOG_FILE")"

run_step() {
    STEP_NAME="$1"
    STEP_SCRIPT="$2"
    echo "" | tee -a "$LOG_FILE"
    echo "[$STEP_NAME] Running $STEP_SCRIPT" | tee -a "$LOG_FILE"
    if [ ! -x "$STEP_SCRIPT" ]; then
        echo "ERROR: script not found or not executable: $STEP_SCRIPT" | tee -a "$LOG_FILE"
        return 1
    fi
    "$STEP_SCRIPT" 2>&1 | tee -a "$LOG_FILE"
    return ${PIPESTATUS:-0}
}

echo "======================================" | tee "$LOG_FILE"
echo "EMS Gateway Network Setup" | tee -a "$LOG_FILE"
echo "NorthBound/Cloudflare Mode" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "======================================" | tee -a "$LOG_FILE"

run_step "1 eth1 field-side" "$ETH1_SCRIPT" || ETH1_RESULT=1
ETH1_RESULT=${ETH1_RESULT:-0}

run_step "2 eth0 application-side" "$ETH0_SCRIPT" || ETH0_RESULT=1
ETH0_RESULT=${ETH0_RESULT:-0}

if [ "$WIFI_ENABLED" = "1" ]; then
    run_step "3 mlan0 Wi-Fi" "$WIFI_SCRIPT" || WIFI_RESULT=1
    WIFI_RESULT=${WIFI_RESULT:-0}
else
    echo "" | tee -a "$LOG_FILE"
    echo "[3 mlan0 Wi-Fi] Skipped because WIFI_ENABLED=$WIFI_ENABLED" | tee -a "$LOG_FILE"
    WIFI_RESULT=0
fi

# Re-assert eth1 because field network must never use default route.
echo "" | tee -a "$LOG_FILE"
echo "[4] Re-applying eth1 field-side route safety after DHCP operations" | tee -a "$LOG_FILE"
"$ETH1_SCRIPT" 2>&1 | tee -a "$LOG_FILE" || ETH1_FINAL_RESULT=1
ETH1_FINAL_RESULT=${ETH1_FINAL_RESULT:-0}

# If eth0 was direct_pc, re-assert it after Wi-Fi DHCP.
# If eth0 was lan_dhcp/auto DHCP, do not blindly overwrite it.
if [ "$ETH0_MODE" = "direct_pc" ]; then
    echo "" | tee -a "$LOG_FILE"
    echo "[5] Re-applying eth0 direct PC/static mode after DHCP operations" | tee -a "$LOG_FILE"
    "$ETH0_SCRIPT" 2>&1 | tee -a "$LOG_FILE" || ETH0_FINAL_RESULT=1
    ETH0_FINAL_RESULT=${ETH0_FINAL_RESULT:-0}
else
    ETH0_FINAL_RESULT="$ETH0_RESULT"
fi

echo "" | tee -a "$LOG_FILE"
echo "[6] Default internet route used by Cloudflare" | tee -a "$LOG_FILE"
ip route get 1.1.1.1 2>&1 | tee -a "$LOG_FILE" || true
ip route get 8.8.8.8 2>&1 | tee -a "$LOG_FILE" || true

echo "" | tee -a "$LOG_FILE"
echo "[7] Final interface status" | tee -a "$LOG_FILE"
ip -br addr show "$ETH0_IFACE" 2>&1 | tee -a "$LOG_FILE" || true
ip -br addr show "$ETH1_IFACE" 2>&1 | tee -a "$LOG_FILE" || true
ip -br addr show "$WIFI_IFACE" 2>&1 | tee -a "$LOG_FILE" || true

echo "" | tee -a "$LOG_FILE"
echo "[8] Field target route checks" | tee -a "$LOG_FILE"
for TARGET in $FIELD_TARGET_IPS; do
    echo "Field target $TARGET" | tee -a "$LOG_FILE"
    ip route get "$TARGET" 2>&1 | tee -a "$LOG_FILE" || true
done

echo "" | tee -a "$LOG_FILE"
echo "[9] Local API checks" | tee -a "$LOG_FILE"
for PORT in "$LOCAL_API_PORT" "$LOCAL_LOGS_PORT"; do
    CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:$PORT/api/health" 2>/dev/null || echo 000)"
    echo "127.0.0.1:$PORT /api/health -> HTTP $CODE" | tee -a "$LOG_FILE"
done

if [ "$CLOUDFLARED_ENABLED" = "1" ]; then
    echo "" | tee -a "$LOG_FILE"
    echo "[10] Cloudflare tunnel status" | tee -a "$LOG_FILE"
    if command -v systemctl >/dev/null 2>&1; then
        if [ "$RESTART_CLOUDFLARED_AFTER_NETWORK" = "1" ]; then
            echo "Restarting cloudflared after network setup..." | tee -a "$LOG_FILE"
            systemctl restart cloudflared 2>&1 | tee -a "$LOG_FILE" || true
            sleep 2
        fi
        systemctl is-active cloudflared 2>&1 | tee -a "$LOG_FILE" || true
        systemctl status cloudflared --no-pager 2>&1 | head -20 | tee -a "$LOG_FILE" || true
    else
        ps aux | grep cloudflared | grep -v grep 2>&1 | tee -a "$LOG_FILE" || true
    fi
fi

echo "" | tee -a "$LOG_FILE"
echo "======================================" | tee -a "$LOG_FILE"
echo "EMS Network Setup Summary" | tee -a "$LOG_FILE"
echo "eth1 field setup result   : $ETH1_RESULT" | tee -a "$LOG_FILE"
echo "eth0 application result   : $ETH0_RESULT" | tee -a "$LOG_FILE"
echo "wifi setup result         : $WIFI_RESULT" | tee -a "$LOG_FILE"
echo "eth1 final result         : $ETH1_FINAL_RESULT" | tee -a "$LOG_FILE"
echo "eth0 final result         : $ETH0_FINAL_RESULT" | tee -a "$LOG_FILE"
echo "Log file                  : $LOG_FILE" | tee -a "$LOG_FILE"
echo "======================================" | tee -a "$LOG_FILE"

if [ "$ETH1_FINAL_RESULT" -ne 0 ] || [ "$ETH0_FINAL_RESULT" -ne 0 ]; then
    echo "ERROR: critical wired network setup failed." | tee -a "$LOG_FILE"
    exit 1
fi

# Wi-Fi failure is not always fatal if eth0 LAN provides internet.
# But we log it clearly.
if [ "$WIFI_RESULT" -ne 0 ]; then
    echo "WARNING: Wi-Fi setup failed. Cloudflare may still work if eth0 LAN has internet." | tee -a "$LOG_FILE"
fi

echo "EMS full network setup completed." | tee -a "$LOG_FILE"
exit 0
