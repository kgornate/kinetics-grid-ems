#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root." >&2
  exit 1
fi

echo "Stopping EMS V3 app stack..."
systemctl disable --now ems-v3-app-stack.target 2>/dev/null || true
systemctl disable --now ems-v3-gateway.service 2>/dev/null || true
systemctl disable --now ems-v3-soc-controller.service 2>/dev/null || true
systemctl disable --now ems-v3-solis-link.service 2>/dev/null || true
systemctl disable --now ems-v3-wifi.service 2>/dev/null || true
systemctl disable --now ems-v3-eth1.service 2>/dev/null || true
systemctl daemon-reload

echo "Package units disabled. Files were not deleted automatically."
echo "Restore from your backup under /root/ems_v3_install_backups if needed."
