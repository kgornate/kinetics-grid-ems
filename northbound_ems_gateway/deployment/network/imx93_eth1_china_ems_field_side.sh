#!/bin/sh
set -eu
# Example only. Update IP values for the actual Chinese EMS field network.
ip link set eth1 up
ip addr flush dev eth1
ip addr add 192.168.1.50/24 dev eth1
# Do not set default route via eth1. It is a field-side local network only.
