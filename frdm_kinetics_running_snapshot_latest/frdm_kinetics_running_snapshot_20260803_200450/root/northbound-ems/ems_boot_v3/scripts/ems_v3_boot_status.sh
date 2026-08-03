#!/bin/sh
# Compact post-boot status screen for Northbound EMS networking.

CONFIG_FILE="/etc/ems_wifi_boot.conf"
[ -f "$CONFIG_FILE" ] && . "$CONFIG_FILE"
WIFI_IFACE="${WIFI_IFACE:-mlan0}"
WIFI_LOG="${WIFI_LOG:-/var/log/ems_wifi_boot.log}"
CF_CONFIG="/etc/cloudflared/config.yml"

service_value() {
    systemctl "$1" "$2" 2>/dev/null || true
}

section() {
    echo
    echo "[$1]"
}

echo "============================================================"
echo "Northbound EMS V3 - Boot and Networking Status"
echo "============================================================"
printf 'Timestamp              : %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
printf 'Uptime                 : %s\n' "$(uptime -p 2>/dev/null || cut -d. -f1 /proc/uptime)"

section "Boot services"
printf 'Wi-Fi service          : %-10s enabled=%s\n' \
    "$(service_value is-active ems-v3-wifi.service)" \
    "$(service_value is-enabled ems-v3-wifi.service)"
printf 'Cloudflare service     : %-10s enabled=%s\n' \
    "$(service_value is-active cloudflared.service)" \
    "$(service_value is-enabled cloudflared.service)"
printf 'SSH socket/service     : %-10s\n' \
    "$(service_value is-active sshd.socket)"

section "Wi-Fi"
SSID="$(iw dev "$WIFI_IFACE" link 2>/dev/null | awk -F': ' '/SSID:/{print $2; exit}')"
SIGNAL="$(iw dev "$WIFI_IFACE" link 2>/dev/null | awk '/signal:/{print $2" "$3; exit}')"
IPV4="$(ip -4 -o addr show dev "$WIFI_IFACE" 2>/dev/null | awk '{print $4; exit}')"
GATEWAY="$(ip -4 route show default dev "$WIFI_IFACE" 2>/dev/null | awk '{print $3; exit}')"
printf 'Interface              : %s\n' "$WIFI_IFACE"
printf 'SSID                   : %s\n' "${SSID:-not connected}"
printf 'Signal                 : %s\n' "${SIGNAL:-unknown}"
printf 'IPv4                   : %s\n' "${IPV4:-none}"
printf 'Default gateway        : %s\n' "${GATEWAY:-none}"

section "Connectivity"
if ping -c 1 -W 3 1.1.1.1 >/dev/null 2>&1; then
    echo "Internet IPv4          : PASS"
else
    echo "Internet IPv4          : FAIL"
fi
if getent hosts region1.v2.argotunnel.com >/dev/null 2>&1; then
    echo "DNS                    : PASS"
else
    echo "DNS                    : FAIL"
fi

section "Cloudflare tunnel"
if [ -r "$CF_CONFIG" ]; then
    TUNNEL_ID="$(awk '/^[[:space:]]*tunnel:/{sub(/^[[:space:]]*tunnel:[[:space:]]*/,""); print; exit}' "$CF_CONFIG")"
    HOSTS="$(awk '/^[[:space:]]*hostname:/{sub(/^[[:space:]]*hostname:[[:space:]]*/,""); print}' "$CF_CONFIG")"
    printf 'Tunnel ID              : %s\n' "${TUNNEL_ID:-unknown}"
    if [ -n "$HOSTS" ]; then
        echo "Published hostnames    :"
        echo "$HOSTS" | sed 's/^/  - /'
    else
        echo "Published hostnames    : none found"
    fi
else
    echo "Configuration          : MISSING ($CF_CONFIG)"
fi

CF_PID="$(pgrep -o cloudflared 2>/dev/null || true)"
printf 'Process                : %s\n' "${CF_PID:+running (PID $CF_PID)}"
[ -n "$CF_PID" ] || echo "Process                : not running"

if journalctl -u cloudflared.service -b --no-pager 2>/dev/null | grep -q 'Registered tunnel connection'; then
    COUNT="$(journalctl -u cloudflared.service -b --no-pager 2>/dev/null | grep -c 'Registered tunnel connection')"
    echo "Tunnel registration    : PASS ($COUNT connection event(s) this boot)"
    journalctl -u cloudflared.service -b --no-pager 2>/dev/null \
        | grep 'Registered tunnel connection' | tail -n 4
else
    echo "Tunnel registration    : NOT YET REGISTERED"
fi

section "SSH listener"
if ss -lnt 2>/dev/null | grep -qE '[:.]22[[:space:]]'; then
    echo "TCP port 22            : LISTENING"
else
    echo "TCP port 22            : NOT LISTENING"
fi

section "Recent Wi-Fi boot log"
tail -n 12 "$WIFI_LOG" 2>/dev/null || echo "No Wi-Fi boot log found"

section "Recent Cloudflare log"
journalctl -u cloudflared.service -b -n 20 --no-pager 2>/dev/null || echo "No Cloudflare log found"
echo "============================================================"
