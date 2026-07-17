#!/bin/sh
set -eu

. /etc/ems_boot_v3.conf

IFACE="${WIFI_IFACE:-mlan0}"
PRIMARY_SSID="${WIFI_PRIMARY_SSID:-}"
PRIMARY_PASS="${WIFI_PRIMARY_PASSWORD:-}"
BACKUP_SSID="${WIFI_BACKUP_SSID:-}"
BACKUP_PASS="${WIFI_BACKUP_PASSWORD:-}"
METRIC="${WIFI_METRIC:-10}"

STATIC_ENABLED="${WIFI_STATIC_FALLBACK_ENABLED:-1}"
STATIC_ADDR="${WIFI_STATIC_ADDR:-192.168.1.103/24}"
STATIC_GW="${WIFI_STATIC_GW:-192.168.1.1}"

DNS1_V="${DNS1:-192.168.1.1}"
DNS2_V="${DNS2:-8.8.8.8}"
DNS3_V="${DNS3:-8.8.4.4}"

ETH1_IF="${ETH1_IFACE:-eth1}"
ETH1_ADDR_CIDR="${ETH1_ADDR:-192.168.100.2/24}"
ETH1_IP="${ETH1_ADDR_CIDR%/*}"
FIELD1="${FIELD_TARGET_1:-192.168.100.151}"
FIELD2="${FIELD_TARGET_2:-192.168.100.153}"

LOG="/var/log/ems_boot_v3_wifi.log"
WPA_CONF="/tmp/ems_v3_wpa.conf"
WPA_LOG="/tmp/ems_v3_wpa.log"

mkdir -p /var/log
touch "$LOG"

log() {
    echo "$(date) [wifi-v3] $*" | tee -a "$LOG"
}

write_dns() {
    cat > /etc/resolv.conf <<DNS
nameserver $DNS1_V
nameserver $DNS2_V
nameserver $DNS3_V
DNS
}

preserve_eth1_routes() {
    ip route replace "$FIELD1" dev "$ETH1_IF" src "$ETH1_IP" 2>/dev/null || true
    ip route replace "$FIELD2" dev "$ETH1_IF" src "$ETH1_IP" 2>/dev/null || true
}

remove_wrong_default_routes() {
    ip route del default dev eth0 2>/dev/null || true
    ip route del default via 192.168.100.1 dev eth0 2>/dev/null || true

    ip route del default dev "$ETH1_IF" 2>/dev/null || true
    ip route del default via 192.168.100.1 dev "$ETH1_IF" 2>/dev/null || true
}

wait_for_iface() {
    i=1
    while [ "$i" -le 20 ]; do
        if ip link show "$IFACE" >/dev/null 2>&1; then
            log "interface $IFACE found"
            return 0
        fi
        log "waiting for interface $IFACE ($i/20)"
        sleep 2
        i=$((i+1))
    done
    log "interface $IFACE not found"
    return 1
}

cleanup_wifi_only() {
    pkill -f "wpa_supplicant.*$IFACE" 2>/dev/null || true
    pkill -f "udhcpc.*$IFACE" 2>/dev/null || true
    sleep 1

    ip addr flush dev "$IFACE" 2>/dev/null || true
    ifconfig "$IFACE" down 2>/dev/null || true
    sleep 1
    ifconfig "$IFACE" up 2>/dev/null || true
    sleep 2

    iw dev "$IFACE" set power_save off 2>/dev/null || true

    rm -rf /var/run/wpa_supplicant
    mkdir -p /var/run/wpa_supplicant
    rm -f "$WPA_LOG" "$WPA_CONF"
}

wait_for_assoc() {
    i=1
    while [ "$i" -le 15 ]; do
        STATE="$(wpa_cli -p /var/run/wpa_supplicant -i "$IFACE" status 2>/dev/null | awk -F= '/^wpa_state=/{print $2}')"
        [ -z "$STATE" ] && STATE="NO_STATUS"
        log "assoc attempt $i/15 state=$STATE"
        if [ "$STATE" = "COMPLETED" ]; then
            return 0
        fi
        sleep 2
        i=$((i+1))
    done
    return 1
}

set_default_via_mlan0() {
    GW="$1"
    remove_wrong_default_routes
    ip route del default dev "$IFACE" 2>/dev/null || true
    ip route del default via "$GW" dev "$IFACE" 2>/dev/null || true
    ip route replace default via "$GW" dev "$IFACE" metric "$METRIC"
    preserve_eth1_routes
    write_dns
}

start_wpa_for_ssid() {
    SSID="$1"
    PASS="$2"

    [ -n "$SSID" ] || return 1

    log "trying ssid=$SSID"

    cat > "$WPA_CONF" <<WPA
ctrl_interface=/var/run/wpa_supplicant
update_config=1
country=IN

network={
    ssid="$SSID"
    psk="$PASS"
    key_mgmt=WPA-PSK
}
WPA
    chmod 600 "$WPA_CONF"

    if ! wpa_supplicant -B -Dnl80211,wext -i "$IFACE" -c "$WPA_CONF" -f "$WPA_LOG"; then
        log "wpa_supplicant start failed for ssid=$SSID"
        cat "$WPA_LOG" 2>/dev/null | tee -a "$LOG" || true
        return 1
    fi

    sleep 3

    if ! wait_for_assoc; then
        log "association failed for ssid=$SSID"
        cat "$WPA_LOG" 2>/dev/null | tail -n 40 | tee -a "$LOG" || true
        pkill -f "wpa_supplicant.*$IFACE" 2>/dev/null || true
        return 1
    fi

    return 0
}

dhcp_or_static() {
    log "starting DHCP on $IFACE"
    pkill -f "udhcpc.*$IFACE" 2>/dev/null || true
    udhcpc -i "$IFACE" -v -q -n -T 3 -t 5 >> "$LOG" 2>&1 || true

    if ip -4 addr show "$IFACE" | grep -q "inet "; then
        GW="$(ip route | awk '$1=="default" && $5=="'"$IFACE"'" {print $3; exit}')"
        [ -z "$GW" ] && GW="$STATIC_GW"
        set_default_via_mlan0 "$GW"
        return 0
    fi

    if [ "$STATIC_ENABLED" = "1" ]; then
        log "DHCP failed, applying static fallback $STATIC_ADDR"
        ip addr flush dev "$IFACE" 2>/dev/null || true
        ip addr add "$STATIC_ADDR" dev "$IFACE"
        set_default_via_mlan0 "$STATIC_GW"
        return 0
    fi

    return 1
}

log "======================================"
log "Minimal Wi-Fi bringup started"

modprobe moal mod_para=nxp/wifi_mod_para.conf
sleep 2

if ! wait_for_iface; then
    exit 1
fi

ifconfig "$IFACE" up 2>/dev/null || true
sleep 2
iw dev "$IFACE" set power_save off 2>/dev/null || true

cleanup_wifi_only

if start_wpa_for_ssid "$PRIMARY_SSID" "$PRIMARY_PASS"; then
    :
elif [ -n "$BACKUP_SSID" ] && [ "$BACKUP_SSID" != "$PRIMARY_SSID" ]; then
    cleanup_wifi_only
    if ! start_wpa_for_ssid "$BACKUP_SSID" "$BACKUP_PASS"; then
        log "both primary and backup association failed"
        exit 1
    fi
else
    log "primary association failed"
    exit 1
fi

if ! dhcp_or_static; then
    log "addressing failed"
    exit 1
fi

preserve_eth1_routes

log "final status"
iw dev "$IFACE" link | tee -a "$LOG" || true
ip -br addr show "$IFACE" | tee -a "$LOG"
ip route | tee -a "$LOG"

ping -I "$IFACE" -c 3 8.8.8.8 >> "$LOG" 2>&1 || true

log "Minimal Wi-Fi bringup completed"
log "======================================"
