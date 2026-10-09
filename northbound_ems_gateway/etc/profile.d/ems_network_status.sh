#!/bin/sh

# Show only for interactive shells
case "$-" in
  *i*) ;;
  *) return 0 2>/dev/null || exit 0 ;;
esac

# Print latest V3 network + gateway status banners
/root/kinetics-grid-ems/ems_network_bootup/profile/ems_network_status.sh 2>/dev/null || true
/root/kinetics-grid-ems/ems_network_bootup/nb_ems_gateway_status.sh 2>/dev/null || true
