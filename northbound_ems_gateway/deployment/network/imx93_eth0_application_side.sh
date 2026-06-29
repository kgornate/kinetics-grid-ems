#!/bin/sh
set -eu
# Application side: local Flutter dashboard direct link OR internet/server uplink.
# Option A: DHCP from router/site LAN
ip link set eth0 up
udhcpc -i eth0 || true
# Option B for direct PC link can be configured manually:
# ip addr flush dev eth0
# ip addr add 192.168.10.2/24 dev eth0
