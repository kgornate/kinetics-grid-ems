#!/bin/sh

# ==========================================================
# i.MX93 EMS Gateway - Wi-Fi Setup with Fallback
#
# Primary Wi-Fi:
#   WIFI_PRIMARY_SSID / WIFI_PRIMARY_PASSWORD
#
# Backup Wi-Fi:
#   WIFI_BACKUP_SSID / WIFI_BACKUP_PASSWORD
#
# Config file:
#   /etc/ems_wifi.conf
# ==========================================================

set -eu

WIFI_IFACE="mlan0"
WIFI_CONFIG="/etc/ems_wifi.conf"
WPA_CONF="/etc/wpa_supplicant.conf"

ETH0_IP="192.168.10.2"
ETH1_IP="192.168.1.2"

PC_SUBNET="192.168.10.0/24"
PCS_SUBNET="192.168.1.0/24"

PC_IP="192.168.10.1"
PCS_IP="192.168.1.200"
DNS_TEST_IP="8.8.8.8"

echo "======================================"
echo "i.MX93 Wi-Fi Setup with Fallback"
echo "======================================"

if [ ! -f "$WIFI_CONFIG" ]; then
    echo "ERROR: Wi-Fi config file not found: $WIFI_CONFIG"
    exit 1
fi

. "$WIFI_CONFIG"

WIFI_PRIMARY_SSID="${WIFI_PRIMARY_SSID:-${WIFI_SSID:-}}"
WIFI_PRIMARY_PASSWORD="${WIFI_PRIMARY_PASSWORD:-${WIFI_PASSWORD:-}}"
WIFI_BACKUP_SSID="${WIFI_BACKUP_SSID:-}"
WIFI_BACKUP_PASSWORD="${WIFI_BACKUP_PASSWORD:-}"

if [ -z "$WIFI_PRIMARY_SSID" ] || [ -z "$WIFI_PRIMARY_PASSWORD" ]; then
    echo "ERROR: Primary Wi-Fi SSID/password missing in /etc/ems_wifi.conf"
    exit 1
fi

echo "Wi-Fi Interface : $WIFI_IFACE"
echo "Primary SSID    : $WIFI_PRIMARY_SSID"
echo "Backup SSID     : $WIFI_BACKUP_SSID"
echo "======================================"

echo ""
echo "[1] Loading NXP Wi-Fi driver..."
modprobe moal mod_para=nxp/wifi_mod_para.conf 2>/dev/null || true
sleep 2

echo ""
echo "[2] Checking Wi-Fi interface..."
if ! ip link show "$WIFI_IFACE" >/dev/null 2>&1; then
    echo "ERROR: Interface $WIFI_IFACE not found"
    ip -br link
    exit 1
fi

echo ""
echo "[3] Bringing Wi-Fi interface up..."
ifconfig "$WIFI_IFACE" up 2>/dev/null || ip link set "$WIFI_IFACE" up

try_wifi()
{
    TRY_LABEL="$1"
    TRY_SSID="$2"
    TRY_PASSWORD="$3"

    echo ""
    echo "--------------------------------------"
    echo "Trying $TRY_LABEL Wi-Fi: $TRY_SSID"
    echo "--------------------------------------"

    killall wpa_supplicant 2>/dev/null || true
    sleep 1

    rm -rf /var/run/wpa_supplicant
    mkdir -p /var/run/wpa_supplicant

    ip addr flush dev "$WIFI_IFACE" 2>/dev/null || true
    ifconfig "$WIFI_IFACE" up 2>/dev/null || ip link set "$WIFI_IFACE" up

    cat > "$WPA_CONF" <<EOC
ctrl_interface=/var/run/wpa_supplicant
update_config=1
country=IN

network={
    ssid="$TRY_SSID"
    psk="$TRY_PASSWORD"
    key_mgmt=WPA-PSK
}
EOC

    chmod 600 "$WPA_CONF"

    echo "[A] Starting wpa_supplicant..."
    wpa_supplicant -B -Dnl80211,wext -i "$WIFI_IFACE" -c "$WPA_CONF"
    sleep 2

    echo "[B] Waiting for Wi-Fi association..."

    WIFI_CONNECTED=0

    for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
        WPA_STATUS="$(wpa_cli -p /var/run/wpa_supplicant -i "$WIFI_IFACE" status 2>/dev/null || true)"
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

    echo "Wi-Fi association completed for SSID: $TRY_SSID"

    echo "[C] Requesting DHCP IP..."
    if ! udhcpc -i "$WIFI_IFACE" -q -n; then
        echo "DHCP failed for SSID: $TRY_SSID"
        killall wpa_supplicant 2>/dev/null || true
        return 1
    fi

    echo "[D] Setting DNS..."
    cat > /etc/resolv.conf <<EOC
nameserver 8.8.8.8
nameserver 1.1.1.1
EOC

    echo "[E] Checking Wi-Fi IP..."
    ip -br addr show "$WIFI_IFACE" || true

    echo "[F] Testing internet through Wi-Fi..."
    if ping -I "$WIFI_IFACE" -c 2 -W 3 "$DNS_TEST_IP" >/dev/null 2>&1; then
        echo "Internet check passed for SSID: $TRY_SSID"
        return 0
    fi

    echo "Internet check failed for SSID: $TRY_SSID"
    killall wpa_supplicant 2>/dev/null || true
    return 1
}

echo ""
echo "[4] Trying primary Wi-Fi first..."
if try_wifi "PRIMARY" "$WIFI_PRIMARY_SSID" "$WIFI_PRIMARY_PASSWORD"; then
    CONNECTED_WIFI="$WIFI_PRIMARY_SSID"
else
    echo ""
    echo "Primary Wi-Fi failed."

    if [ -n "$WIFI_BACKUP_SSID" ] && [ -n "$WIFI_BACKUP_PASSWORD" ]; then
        echo "Trying backup Wi-Fi..."
        if try_wifi "BACKUP" "$WIFI_BACKUP_SSID" "$WIFI_BACKUP_PASSWORD"; then
            CONNECTED_WIFI="$WIFI_BACKUP_SSID"
        else
            echo "ERROR: Both primary and backup Wi-Fi failed"
            exit 1
        fi
    else
        echo "ERROR: Backup Wi-Fi not configured"
        exit 1
    fi
fi

echo ""
echo "[5] Connected Wi-Fi SSID:"
echo "$CONNECTED_WIFI"

echo ""
echo "[6] Restoring EMS local routes..."
ip route replace "$PC_SUBNET" dev eth0 src "$ETH0_IP" 2>/dev/null || true
ip route replace "$PCS_SUBNET" dev eth1 src "$ETH1_IP" 2>/dev/null || true

echo ""
echo "[7] Final Wi-Fi status:"
wpa_cli -p /var/run/wpa_supplicant -i "$WIFI_IFACE" status || true

echo ""
echo "[8] Final interface status:"
ip -br addr show eth0 || true
ip -br addr show eth1 || true
ip -br addr show "$WIFI_IFACE" || true

echo ""
echo "[9] Final route check:"
ip route get "$PC_IP" || true
ip route get "$PCS_IP" || true
ip route get "$DNS_TEST_IP" || true

echo ""
echo "[10] DNS check:"
ping -I "$WIFI_IFACE" -c 2 google.com || true

echo ""
echo "======================================"
echo "Wi-Fi setup completed"
echo "Active SSID: $CONNECTED_WIFI"
echo "======================================"
