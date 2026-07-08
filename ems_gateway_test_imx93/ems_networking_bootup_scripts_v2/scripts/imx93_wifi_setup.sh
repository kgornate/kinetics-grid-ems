#!/bin/sh
# ==========================================================
# i.MX93 Wi-Fi Setup with Primary/Backup Wi-Fi
# Improved version:
#   - waits for mlan0 readiness
#   - gives wpa_supplicant more time
#   - retries DHCP multiple times
#   - optional static fallback after association
# ==========================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/ems_common.sh"
load_config

WPA_CONF="/etc/wpa_supplicant.conf"
IFACE="${WIFI_IFACE:-mlan0}"

WIFI_CONNECT_ATTEMPTS="${WIFI_CONNECT_ATTEMPTS:-30}"
WIFI_CONNECT_SLEEP_SEC="${WIFI_CONNECT_SLEEP_SEC:-2}"
WIFI_DHCP_ATTEMPTS="${WIFI_DHCP_ATTEMPTS:-3}"
WIFI_DHCP_TRIES_PER_ATTEMPT="${WIFI_DHCP_TRIES_PER_ATTEMPT:-20}"
WIFI_DHCP_TIMEOUT_SEC="${WIFI_DHCP_TIMEOUT_SEC:-3}"

# Optional static fallback after Wi-Fi association if DHCP fails.
# To enable, add these in /etc/ems_network.conf:
# WIFI_STATIC_FALLBACK_ENABLED="1"
# WIFI_STATIC_IP="192.168.1.100/24"
# WIFI_STATIC_GATEWAY="192.168.1.1"
WIFI_STATIC_FALLBACK_ENABLED="${WIFI_STATIC_FALLBACK_ENABLED:-0}"
WIFI_STATIC_IP="${WIFI_STATIC_IP:-192.168.1.100/24}"
WIFI_STATIC_GATEWAY="${WIFI_STATIC_GATEWAY:-192.168.1.1}"

cat <<EOM
======================================
i.MX93 Wi-Fi Setup
======================================
Enabled         : $WIFI_ENABLED
Wi-Fi Interface : $IFACE
Primary SSID    : $WIFI_PRIMARY_SSID
Backup SSID     : $WIFI_BACKUP_SSID
Metric          : $WIFI_METRIC
DHCP attempts   : $WIFI_DHCP_ATTEMPTS
Connect attempts: $WIFI_CONNECT_ATTEMPTS
Static fallback : $WIFI_STATIC_FALLBACK_ENABLED
======================================
EOM

if [ "$WIFI_ENABLED" != "1" ]; then
    echo "Wi-Fi disabled by config."
    exit 0
fi

if [ -z "$WIFI_PRIMARY_SSID" ] || [ -z "$WIFI_PRIMARY_PASSWORD" ]; then
    echo "ERROR: Primary Wi-Fi SSID/password missing in /etc/ems_network.conf"
    exit 1
fi

wait_for_iface() {
    echo "[wifi] Waiting for interface $IFACE..."

    for i in $(seq 1 30); do
        if ip link show "$IFACE" >/dev/null 2>&1; then
            echo "[wifi] Interface $IFACE found"
            return 0
        fi
        echo "[wifi] Waiting for $IFACE... attempt $i"
        sleep 1
    done

    echo "ERROR: Interface $IFACE not found"
    ip -br link || true
    return 1
}

bring_iface_up() {
    ip link set "$IFACE" up 2>/dev/null || ifconfig "$IFACE" up 2>/dev/null || true
    sleep 2
}

cleanup_wifi_processes() {
    pkill -f "wpa_supplicant.*$IFACE" 2>/dev/null || true
    pkill -f "udhcpc.*$IFACE" 2>/dev/null || true
    sleep 1
}

write_dns() {
    GW="$(ip route show dev "$IFACE" 2>/dev/null | awk '/default/ {print $3; exit}')"

    {
        if [ -n "$GW" ]; then
            echo "nameserver $GW"
        fi
        echo "nameserver 8.8.8.8"
        echo "nameserver 1.1.1.1"
    } > /etc/resolv.conf
}

check_internet() {
    echo "[wifi] Internet check using $IFACE..."

    if ping -I "$IFACE" -c 2 -W 3 "$DNS_TEST_IP" >/dev/null 2>&1; then
        echo "Internet check passed"
        return 0
    fi

    echo "Internet check failed"
    return 1
}

apply_static_fallback() {
    if [ "$WIFI_STATIC_FALLBACK_ENABLED" != "1" ]; then
        return 1
    fi

    echo "[wifi] Applying static fallback..."
    echo "[wifi] Static IP      : $WIFI_STATIC_IP"
    echo "[wifi] Static gateway : $WIFI_STATIC_GATEWAY"

    ip addr flush dev "$IFACE" 2>/dev/null || true
    ip addr add "$WIFI_STATIC_IP" dev "$IFACE"
    ip route replace default via "$WIFI_STATIC_GATEWAY" dev "$IFACE" metric "$WIFI_METRIC"

    write_dns

    echo "[wifi] Interface status after static fallback:"
    ip -br addr show "$IFACE" || true
    ip route || true

    if ping -I "$IFACE" -c 2 -W 3 "$WIFI_STATIC_GATEWAY" >/dev/null 2>&1; then
        echo "[wifi] Static fallback gateway check passed"
        if check_internet; then
            return 0
        fi
    fi

    echo "[wifi] Static fallback failed"
    return 1
}

run_dhcp_with_retries() {
    echo "[wifi] DHCP request with retries..."

    ip addr flush dev "$IFACE" 2>/dev/null || true

    for i in $(seq 1 "$WIFI_DHCP_ATTEMPTS"); do
        echo "[wifi] DHCP attempt $i/$WIFI_DHCP_ATTEMPTS"

        pkill -f "udhcpc.*$IFACE" 2>/dev/null || true
        sleep 1

        udhcpc -i "$IFACE" -v -q -n -T "$WIFI_DHCP_TIMEOUT_SEC" -t "$WIFI_DHCP_TRIES_PER_ATTEMPT"

        if ip -4 addr show "$IFACE" | grep -q "inet "; then
            echo "[wifi] DHCP success"
            set_default_metric_if_present "$IFACE" "$WIFI_METRIC"
            write_dns
            return 0
        fi

        echo "[wifi] DHCP attempt $i failed"
        sleep 5
    done

    echo "[wifi] DHCP failed after all attempts"
    return 1
}

try_wifi() {
    TRY_LABEL="$1"
    TRY_SSID="$2"
    TRY_PASSWORD="$3"

    echo ""
    echo "--------------------------------------"
    echo "Trying $TRY_LABEL Wi-Fi: $TRY_SSID"
    echo "--------------------------------------"

    cleanup_wifi_processes

    rm -rf /var/run/wpa_supplicant
    mkdir -p /var/run/wpa_supplicant

    ip addr flush dev "$IFACE" 2>/dev/null || true
    bring_iface_up

    cat > "$WPA_CONF" <<EOC
ctrl_interface=/var/run/wpa_supplicant
update_config=1
country=$WIFI_CONFIG_COUNTRY

network={
    ssid="$TRY_SSID"
    psk="$TRY_PASSWORD"
    key_mgmt=WPA-PSK
}
EOC
    chmod 600 "$WPA_CONF"

    echo "[wifi] Starting wpa_supplicant..."
    if ! wpa_supplicant -B -Dnl80211,wext -i "$IFACE" -c "$WPA_CONF"; then
        echo "wpa_supplicant failed for SSID: $TRY_SSID"
        cleanup_wifi_processes
        return 1
    fi

    sleep 3

    WIFI_CONNECTED=0

    for i in $(seq 1 "$WIFI_CONNECT_ATTEMPTS"); do
        WPA_STATUS="$(wpa_cli -p /var/run/wpa_supplicant -i "$IFACE" status 2>/dev/null || true)"
        WPA_STATE="$(echo "$WPA_STATUS" | grep '^wpa_state=' | cut -d= -f2 || true)"

        if [ -z "$WPA_STATE" ]; then
            WPA_STATE="NO_STATUS"
        fi

        echo "Attempt $i: wpa_state=$WPA_STATE"

        if [ "$WPA_STATE" = "COMPLETED" ]; then
            WIFI_CONNECTED=1
            break
        fi

        # Ask supplicant to retry scan/association every few attempts.
        if [ $((i % 5)) -eq 0 ]; then
            wpa_cli -p /var/run/wpa_supplicant -i "$IFACE" reassociate >/dev/null 2>&1 || true
        fi

        sleep "$WIFI_CONNECT_SLEEP_SEC"
    done

    if [ "$WIFI_CONNECTED" -ne 1 ]; then
        echo "Wi-Fi association failed for SSID: $TRY_SSID"
        cleanup_wifi_processes
        return 1
    fi

    echo "[wifi] Association completed for SSID: $TRY_SSID"
    sleep 3

    if run_dhcp_with_retries; then
        echo "[wifi] Interface status:"
        ip -br addr show "$IFACE" || true

        if check_internet; then
            echo "Internet check passed for SSID: $TRY_SSID"
            return 0
        fi

        echo "Internet check failed for SSID: $TRY_SSID"
        return 1
    fi

    echo "DHCP failed for SSID: $TRY_SSID"

    if apply_static_fallback; then
        echo "Static fallback passed for SSID: $TRY_SSID"
        return 0
    fi

    cleanup_wifi_processes
    return 1
}

# Load NXP Wi-Fi driver if available.
modprobe moal mod_para=nxp/wifi_mod_para.conf 2>/dev/null || true
sleep 3

wait_for_iface || exit 1
bring_iface_up

if try_wifi "PRIMARY" "$WIFI_PRIMARY_SSID" "$WIFI_PRIMARY_PASSWORD"; then
    CONNECTED_WIFI="$WIFI_PRIMARY_SSID"
else
    echo "Primary Wi-Fi failed."

    if [ -n "$WIFI_BACKUP_SSID" ] && [ -n "$WIFI_BACKUP_PASSWORD" ]; then
        if try_wifi "BACKUP" "$WIFI_BACKUP_SSID" "$WIFI_BACKUP_PASSWORD"; then
            CONNECTED_WIFI="$WIFI_BACKUP_SSID"
        else
            echo "ERROR: both primary and backup Wi-Fi failed"
            exit 1
        fi
    else
        echo "ERROR: backup Wi-Fi not configured"
        exit 1
    fi
fi

echo ""
echo "[wifi] Connected SSID: $CONNECTED_WIFI"
wpa_cli -p /var/run/wpa_supplicant -i "$IFACE" status || true

echo "======================================"
echo "Wi-Fi setup completed"
echo "======================================"
EOF

chmod +x "$SCRIPT"
sh -n "$SCRIPT"

echo "Updated script:"
ls -l "$SCRIPT"