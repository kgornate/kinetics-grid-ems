#!/bin/sh
# ==========================================================
# EMS Boot V3 - FRDM-i.MX93 Wi-Fi setup
# Primary/backup Wi-Fi, DHCP, DNS verification and logging.
# ==========================================================

set -u

CONFIG_FILE="/etc/ems_wifi_boot.conf"
[ -f "$CONFIG_FILE" ] && . "$CONFIG_FILE"

WIFI_ENABLED="${WIFI_ENABLED:-1}"
WIFI_IFACE="${WIFI_IFACE:-mlan0}"
WIFI_COUNTRY="${WIFI_COUNTRY:-IN}"
WIFI_PRIMARY_SSID="${WIFI_PRIMARY_SSID:-}"
WIFI_PRIMARY_PASSWORD="${WIFI_PRIMARY_PASSWORD:-}"
WIFI_BACKUP_SSID="${WIFI_BACKUP_SSID:-}"
WIFI_BACKUP_PASSWORD="${WIFI_BACKUP_PASSWORD:-}"
WIFI_CONNECT_ATTEMPTS="${WIFI_CONNECT_ATTEMPTS:-3}"
WIFI_ASSOC_TIMEOUT_SEC="${WIFI_ASSOC_TIMEOUT_SEC:-30}"
WIFI_DHCP_ATTEMPTS="${WIFI_DHCP_ATTEMPTS:-5}"
WIFI_DHCP_TIMEOUT_SEC="${WIFI_DHCP_TIMEOUT_SEC:-5}"
DNS1="${DNS1:-1.1.1.1}"
DNS2="${DNS2:-8.8.8.8}"
WIFI_LOG="${WIFI_LOG:-/var/log/ems_wifi_boot.log}"

WPA_RUNTIME="/var/run/wpa_supplicant"
WPA_CONFIG="/run/ems-wpa-${WIFI_IFACE}.conf"

mkdir -p "$(dirname "$WIFI_LOG")" "$WPA_RUNTIME" /run

log() {
    LINE="$(date '+%Y-%m-%d %H:%M:%S') [ems-v3-wifi] $*"
    echo "$LINE"
    echo "$LINE" >> "$WIFI_LOG"
}

if [ "$WIFI_ENABLED" != "1" ]; then
    log "Wi-Fi disabled in $CONFIG_FILE"
    exit 0
fi

log "======================================"
log "EMS V3 Wi-Fi boot setup"
log "Interface: $WIFI_IFACE"
log "Primary SSID: $WIFI_PRIMARY_SSID"
log "Backup SSID: $WIFI_BACKUP_SSID"
log "======================================"

# Driver is normally loaded automatically by the NXP BSP.
# Reload only if mlan0 is missing.
if ! ip link show "$WIFI_IFACE" >/dev/null 2>&1; then
    log "$WIFI_IFACE missing; loading NXP moal driver"
    modprobe moal mod_para=nxp/wifi_mod_para.conf 2>>"$WIFI_LOG" || modprobe moal 2>>"$WIFI_LOG" || true
fi

WAIT=0
while ! ip link show "$WIFI_IFACE" >/dev/null 2>&1; do
    WAIT=$((WAIT + 1))
    [ "$WAIT" -ge 30 ] && { log "ERROR: $WIFI_IFACE did not appear"; exit 1; }
    sleep 2
done

# This custom service owns mlan0. Avoid ConnMan/system wpa_supplicant conflicts.
systemctl stop connman.service 2>/dev/null || true
systemctl stop wpa_supplicant.service 2>/dev/null || true
killall wpa_supplicant 2>/dev/null || true
killall udhcpc 2>/dev/null || true
rm -rf "$WPA_RUNTIME"
mkdir -p "$WPA_RUNTIME"

ip addr flush dev "$WIFI_IFACE" 2>/dev/null || true
ip route flush dev "$WIFI_IFACE" 2>/dev/null || true
ip link set "$WIFI_IFACE" down 2>/dev/null || true
sleep 1
ip link set "$WIFI_IFACE" up
sleep 2
iw dev "$WIFI_IFACE" set power_save off 2>/dev/null || true

write_config() {
    SSID="$1"
    PASSWORD="$2"
    cat > "$WPA_CONFIG" <<WPAEOF
ctrl_interface=$WPA_RUNTIME
update_config=0
country=$WIFI_COUNTRY

network={
    ssid="$SSID"
    psk="$PASSWORD"
    key_mgmt=WPA-PSK
    scan_ssid=1
}
WPAEOF
    chmod 600 "$WPA_CONFIG"
}

associated() {
    STATE="$(wpa_cli -p "$WPA_RUNTIME" -i "$WIFI_IFACE" status 2>/dev/null | awk -F= '/^wpa_state=/{print $2}')"
    [ "$STATE" = "COMPLETED" ]
}

connect_network() {
    SSID="$1"
    PASSWORD="$2"
    [ -n "$SSID" ] || return 1

    ATTEMPT=1
    while [ "$ATTEMPT" -le "$WIFI_CONNECT_ATTEMPTS" ]; do
        log "Connecting to '$SSID' (attempt $ATTEMPT/$WIFI_CONNECT_ATTEMPTS)"

        killall wpa_supplicant 2>/dev/null || true
        rm -rf "$WPA_RUNTIME"
        mkdir -p "$WPA_RUNTIME"
        write_config "$SSID" "$PASSWORD"

        wpa_supplicant -B -Dnl80211 -i "$WIFI_IFACE" -c "$WPA_CONFIG" >>"$WIFI_LOG" 2>&1 || true

        ELAPSED=0
        while [ "$ELAPSED" -lt "$WIFI_ASSOC_TIMEOUT_SEC" ]; do
            if associated; then
                log "Associated with '$SSID'"
                return 0
            fi
            sleep 2
            ELAPSED=$((ELAPSED + 2))
        done

        log "Association failed for '$SSID'"
        ATTEMPT=$((ATTEMPT + 1))
    done
    return 1
}

if connect_network "$WIFI_PRIMARY_SSID" "$WIFI_PRIMARY_PASSWORD"; then
    CONNECTED_SSID="$WIFI_PRIMARY_SSID"
elif connect_network "$WIFI_BACKUP_SSID" "$WIFI_BACKUP_PASSWORD"; then
    CONNECTED_SSID="$WIFI_BACKUP_SSID"
else
    log "ERROR: both primary and backup Wi-Fi connections failed"
    exit 1
fi

# Obtain DHCP lease.
DHCP_OK=0
DHCP_TRY=1
while [ "$DHCP_TRY" -le "$WIFI_DHCP_ATTEMPTS" ]; do
    log "DHCP request (attempt $DHCP_TRY/$WIFI_DHCP_ATTEMPTS)"
    udhcpc -i "$WIFI_IFACE" -q -n -T "$WIFI_DHCP_TIMEOUT_SEC" -t 3 \
        -s /usr/share/udhcpc/default.script >>"$WIFI_LOG" 2>&1 || true

    if ip -4 addr show "$WIFI_IFACE" | grep -q 'inet '; then
        DHCP_OK=1
        break
    fi
    DHCP_TRY=$((DHCP_TRY + 1))
done

if [ "$DHCP_OK" != "1" ]; then
    log "ERROR: DHCP failed on $WIFI_IFACE"
    exit 1
fi

# DNS fallback if resolution is not working.
if ! getent hosts google.com >/dev/null 2>&1; then
    log "DNS resolution failed; installing fallback resolvers"
    rm -f /etc/resolv.conf
    cat > /etc/resolv.conf <<DNSEOF
nameserver $DNS1
nameserver $DNS2
DNSEOF
fi

log "Connected SSID: $CONNECTED_SSID"
ip -br addr show "$WIFI_IFACE" 2>&1 | while IFS= read -r L; do log "$L"; done
ip route 2>&1 | while IFS= read -r L; do log "$L"; done

if ping -c 2 -W 3 1.1.1.1 >/dev/null 2>&1; then
    log "Internet IPv4 check: PASS"
else
    log "Internet IPv4 check: FAIL"
fi

if getent hosts google.com >/dev/null 2>&1; then
    log "DNS check: PASS"
else
    log "DNS check: FAIL"
fi

log "Wi-Fi boot setup complete"
exit 0
