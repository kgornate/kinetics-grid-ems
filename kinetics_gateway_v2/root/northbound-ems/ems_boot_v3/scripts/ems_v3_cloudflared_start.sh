#!/bin/sh
# Northbound EMS V3 cloudflared launcher.
# Waits for the custom Wi-Fi stack instead of network-online.target,
# which can remain pending on this Yocto image.

set -u

CONFIG="/etc/cloudflared/config.yml"
WIFI_IFACE="${WIFI_IFACE:-mlan0}"
WAIT_STEP_SEC="${CLOUDFLARED_WAIT_STEP_SEC:-3}"
WAIT_TIMEOUT_SEC="${CLOUDFLARED_WAIT_TIMEOUT_SEC:-180}"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ems-v3-cloudflared] $*"
}

find_cloudflared() {
    for p in /bin/cloudflared /usr/bin/cloudflared /usr/local/bin/cloudflared; do
        if [ -x "$p" ]; then
            echo "$p"
            return 0
        fi
    done
    command -v cloudflared 2>/dev/null || return 1
}

BIN="$(find_cloudflared || true)"
if [ -z "$BIN" ]; then
    log "ERROR: cloudflared binary not found"
    exit 1
fi

if [ ! -r "$CONFIG" ]; then
    log "ERROR: missing $CONFIG"
    exit 1
fi

ELAPSED=0
while ! ip -4 route show default dev "$WIFI_IFACE" 2>/dev/null | grep -q '^default'; do
    if [ "$ELAPSED" -ge "$WAIT_TIMEOUT_SEC" ]; then
        log "ERROR: no IPv4 default route on $WIFI_IFACE after ${WAIT_TIMEOUT_SEC}s"
        exit 1
    fi
    log "Waiting for IPv4 default route on $WIFI_IFACE"
    sleep "$WAIT_STEP_SEC"
    ELAPSED=$((ELAPSED + WAIT_STEP_SEC))
done

ELAPSED=0
while ! ping -c 1 -W 3 1.1.1.1 >/dev/null 2>&1; do
    if [ "$ELAPSED" -ge "$WAIT_TIMEOUT_SEC" ]; then
        log "ERROR: Internet connectivity unavailable after ${WAIT_TIMEOUT_SEC}s"
        exit 1
    fi
    log "Waiting for Internet connectivity"
    sleep "$WAIT_STEP_SEC"
    ELAPSED=$((ELAPSED + WAIT_STEP_SEC))
done

log "Starting $BIN with $CONFIG"
exec "$BIN" --no-autoupdate --config "$CONFIG" tunnel run
