#!/bin/sh
set -eu

# Optional helper for Wi-Fi/uplink validation.
# Actual Wi-Fi SSID/password connection is normally handled by the existing BSP
# network service or NetworkManager/wpa_supplicant setup.

IFACE="${1:-mlan0}"
SERVER_HOST="${2:-CHANGE_ME_SERVER_HOST}"

echo "Checking Wi-Fi/server uplink interface: ${IFACE}"
ip link show "${IFACE}" || exit 1
ip -4 addr show dev "${IFACE}" || true
ip route || true

if [ "${SERVER_HOST}" != "CHANGE_ME_SERVER_HOST" ]; then
  echo "Testing HTTPS reachability to ${SERVER_HOST}:443 from current routing table..."
  python3 - <<PY
import socket
host = "${SERVER_HOST}"
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
try:
    s.connect((host, 443))
    print(f"OK: TCP 443 reachable for {host}")
except Exception as exc:
    print(f"FAILED: {exc}")
finally:
    s.close()
PY
else
  echo "Pass server host as second argument to test TCP 443 reachability."
fi
