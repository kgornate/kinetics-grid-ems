#!/bin/sh

CONFIG_FILE="/etc/ems_network.conf"

load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        . "$CONFIG_FILE"
    else
        echo "ERROR: config file not found: $CONFIG_FILE"
        exit 1
    fi
}

log_line() {
    echo "$*"
}

get_ipv4_of_iface() {
    IFACE="$1"
    ip -4 -o addr show dev "$IFACE" 2>/dev/null | awk '{print $4}' | head -1
}

has_carrier() {
    IFACE="$1"
    if [ -f "/sys/class/net/$IFACE/carrier" ]; then
        cat "/sys/class/net/$IFACE/carrier" 2>/dev/null
    else
        echo "unknown"
    fi
}

set_default_metric_if_present() {
    IFACE="$1"
    METRIC="$2"
    GW="$(ip route show default dev "$IFACE" 2>/dev/null | awk '/default/ {print $3; exit}')"
    if [ -n "$GW" ]; then
        ip route replace default via "$GW" dev "$IFACE" metric "$METRIC" 2>/dev/null || true
        echo "Default route on $IFACE via $GW metric $METRIC"
    else
        echo "No default route found on $IFACE"
    fi
}
