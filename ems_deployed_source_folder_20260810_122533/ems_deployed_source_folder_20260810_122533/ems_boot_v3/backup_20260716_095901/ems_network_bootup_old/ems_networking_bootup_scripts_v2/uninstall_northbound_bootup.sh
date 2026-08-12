#!/bin/sh
# Undo NorthBound gateway auto-start and optionally networking boot service.
# This does not delete the northbound_ems_gateway application codebase.
set -u

echo "Stopping/disabling NorthBound Gateway auto-start..."
if command -v systemctl >/dev/null 2>&1; then
    systemctl stop nb-ems-gateway.service 2>/dev/null || true
    systemctl disable nb-ems-gateway.service 2>/dev/null || true
fi
rm -f /etc/systemd/system/nb-ems-gateway.service

# Keep networking boot service by default because it may be needed for the board.
# To remove it too, run this script with: sh uninstall_northbound_bootup.sh --remove-network-service
if [ "${1:-}" = "--remove-network-service" ]; then
    echo "Stopping/disabling EMS network boot service too..."
    if command -v systemctl >/dev/null 2>&1; then
        systemctl stop ems-network-setup.service 2>/dev/null || true
        systemctl disable ems-network-setup.service 2>/dev/null || true
    fi
    rm -f /etc/systemd/system/ems-network-setup.service
fi

if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload
    systemctl reset-failed nb-ems-gateway.service 2>/dev/null || true
    systemctl reset-failed ems-network-setup.service 2>/dev/null || true
fi

echo "Done. The NorthBound application folder was not deleted."
echo "Manual run command remains:"
echo "  cd /root/kinetics-grid-ems/northbound_ems_gateway"
echo "  PYTHONPATH=src python3 -m nb_ems_gateway.main --config configs/development.json --mock"
