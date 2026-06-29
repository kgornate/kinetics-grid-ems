#!/bin/sh
# ==========================================================
# i.MX93 Wi-Fi Setup with Optional Fallback
# mlan0 = Wi-Fi internet for Cloudflare tunnel when eth0 LAN internet
#         is not available.
# ==========================================================

set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/ems_common.sh"
load_config

WPA_CONF="/etc/wpa_supplicant.conf"
IFACE="$WIFI_IFACE"

cat <<EOM
======================================
i.MX93 Wi-Fi Setup
======================================
Enabled         : $WIFI_ENABLED
Wi-Fi Interface : $IFACE
Primary SSID    : $WIFI_PRIMARY_SSID
Backup SSID     : $WIFI_BACKUP_SSID
Metric          : $WIFI_METRIC
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

# Load NXP Wi-Fi driver if available.
modprobe moal mod_para=nxp/wifi_mod_para.conf 2>/dev/null || true
sleep 2

if ! ip link show "$IFACE" >/dev/null 2>&1; then
    echo "ERROR: Interface $IFACE not found"
    ip -br link || true
    exit 1
fi

ifconfig "$IFACE" up 2>/dev/null || ip link set "$IFACE" up

try_wifi() {
    TRY_LABEL="$1"
    TRY_SSID="$2"
    TRY_PASSWORD="$3"

    echo ""
    echo "--------------------------------------"
    echo "Trying $TRY_LABEL Wi-Fi: $TRY_SSID"
    echo "--------------------------------------"

    killall wpa_supplicant 2>/dev/null || true
    pkill -f "udhcpc.*-i $IFACE" 2>/dev/null || true
    sleep 1

    rm -rf /var/run/wpa_supplicant
    mkdir -p /var/run/wpa_supplicant

    ip addr flush dev "$IFACE" 2>/dev/null || true
    ifconfig "$IFACE" up 2>/dev/null || ip link set "$IFACE" up

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
        return 1
    fi
    sleep 2

    WIFI_CONNECTED=0
    for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
        WPA_STATUS="$(wpa_cli -p /var/run/wpa_supplicant -i "$IFACE" status 2>/dev/null || true)"
        WPA_STATE="$(echo "$WPA_STATUS" | grep "wpa_state=" || true)"
        echo "Attempt $i: $WPA_STATE"
        if echo "$WPA_STATUS" | grep -q "wpa_state=COMPLETED"; then
            WIFI_CONNECTED=1
            break
        fi
        sleep 2
    done

    if [ "$WIFI_CONNECTED" -ne 1 ]; then
        echo "Wi-Fi association failed for SSID: $TRY_SSID"
        killall wpa_supplicant 2>/dev/null || true
        return 1
    fi

    echo "[wifi] DHCP request..."
    if ! udhcpc -i "$IFACE" -q -n -T 5 -t 4; then
        echo "DHCP failed for SSID: $TRY_SSID"
        killall wpa_supplicant 2>/dev/null || true
        return 1
    fi

    set_default_metric_if_present "$IFACE" "$WIFI_METRIC"

    cat > /etc/resolv.conf <<EOC
nameserver 8.8.8.8
nameserver 1.1.1.1
EOC

    echo "[wifi] Interface status:"
    ip -br addr show "$IFACE" || true

    echo "[wifi] Internet check using $IFACE..."
    if ping -I "$IFACE" -c 2 -W 3 "$DNS_TEST_IP" >/dev/null 2>&1; then
        echo "Internet check passed for SSID: $TRY_SSID"
        return 0
    fi

    echo "Internet check failed for SSID: $TRY_SSID"
    return 1
}

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
