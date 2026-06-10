#!/bin/sh

# ==========================================================
# i.MX93 EMS Gateway - Wi-Fi Setup
#
# eth0  = PC / Flutter dashboard side
# eth1  = Real PCS Modbus TCP side
# mlan0 = Wi-Fi / internet side
#
# Wi-Fi credentials are stored in:
#   /etc/ems_wifi.conf
#
# Expected /etc/ems_wifi.conf format:
#   WIFI_SSID="YourSSID"
#   WIFI_PASSWORD="YourPassword"
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
echo "i.MX93 Wi-Fi Setup"
echo "======================================"

if [ ! -f "$WIFI_CONFIG" ]; then
    echo "ERROR: Wi-Fi config file not found: $WIFI_CONFIG"
    echo "Create it like:"
    echo 'WIFI_SSID="YourSSID"'
    echo 'WIFI_PASSWORD="YourPassword"'
    exit 1
fi

# Load Wi-Fi credentials
. "$WIFI_CONFIG"

: "${WIFI_SSID:?ERROR: WIFI_SSID missing in /etc/ems_wifi.conf}"
: "${WIFI_PASSWORD:?ERROR: WIFI_PASSWORD missing in /etc/ems_wifi.conf}"

echo "Wi-Fi Interface : $WIFI_IFACE"
echo "Wi-Fi SSID      : $WIFI_SSID"
echo "======================================"

echo ""
echo "[1] Loading NXP Wi-Fi driver..."
modprobe moal mod_para=nxp/wifi_mod_para.conf 2>/dev/null || true
sleep 2

echo ""
echo "[2] Checking Wi-Fi interface..."
if ! ip link show "$WIFI_IFACE" >/dev/null 2>&1; then
    echo "ERROR: Interface $WIFI_IFACE not found"
    echo "Available interfaces:"
    ip -br link
    exit 1
fi

echo ""
echo "[3] Bringing Wi-Fi interface up..."
ifconfig "$WIFI_IFACE" up 2>/dev/null || ip link set "$WIFI_IFACE" up

echo ""
echo "[4] Preparing wpa_supplicant runtime directory..."
rm -rf /var/run/wpa_supplicant
mkdir -p /var/run/wpa_supplicant

echo ""
echo "[5] Creating wpa_supplicant config..."
cat > "$WPA_CONF" <<EOC
ctrl_interface=/var/run/wpa_supplicant
update_config=1
country=IN

EOC

if command -v wpa_passphrase >/dev/null 2>&1; then
    wpa_passphrase "$WIFI_SSID" "$WIFI_PASSWORD" | grep -v '#psk=' >> "$WPA_CONF"
else
    cat >> "$WPA_CONF" <<EOC
network={
    ssid="$WIFI_SSID"
    psk="$WIFI_PASSWORD"
    key_mgmt=WPA-PSK
}
EOC
fi

chmod 600 "$WPA_CONF"

echo ""
echo "[6] Restarting wpa_supplicant..."
killall wpa_supplicant 2>/dev/null || true
sleep 1

wpa_supplicant -B -Dnl80211,wext -i "$WIFI_IFACE" -c "$WPA_CONF"
sleep 2

echo ""
echo "[7] Waiting for Wi-Fi association..."

WIFI_CONNECTED=0

# Wait up to 40 seconds for connection
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
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
    echo ""
    echo "ERROR: Wi-Fi association failed"
    echo "Final WPA status:"
    wpa_cli -p /var/run/wpa_supplicant -i "$WIFI_IFACE" status || true
    exit 1
fi

echo "Wi-Fi association completed."

echo ""
echo "[8] Requesting DHCP IP..."
udhcpc -i "$WIFI_IFACE" -q -n || {
    echo "ERROR: DHCP failed on $WIFI_IFACE"
    exit 1
}

echo ""
echo "[9] Setting DNS..."
cat > /etc/resolv.conf <<EOC
nameserver 8.8.8.8
nameserver 1.1.1.1
EOC

echo ""
echo "[10] Restoring EMS local routes..."
ip route replace "$PC_SUBNET" dev eth0 src "$ETH0_IP" 2>/dev/null || true
ip route replace "$PCS_SUBNET" dev eth1 src "$ETH1_IP" 2>/dev/null || true

echo ""
echo "[11] Final interface status:"
ip -br addr show eth0 || true
ip -br addr show eth1 || true
ip -br addr show "$WIFI_IFACE" || true

echo ""
echo "[12] Final route check:"
ip route get "$PC_IP" || true
ip route get "$PCS_IP" || true
ip route get "$DNS_TEST_IP" || true

echo ""
echo "[13] DNS check:"
ping -I "$WIFI_IFACE" -c 2 google.com || true

echo ""
echo "======================================"
echo "Wi-Fi setup completed"
echo "======================================"
