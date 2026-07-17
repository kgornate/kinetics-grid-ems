#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
FILES_DIR="$ROOT/files"
BACKUP_ROOT="/root/ems_v3_install_backups"
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/$TS"

need_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root." >&2
    exit 1
  fi
}

backup_if_exists() {
  local target="$1"
  if [ -e "$target" ] || [ -L "$target" ]; then
    mkdir -p "$BACKUP_DIR$(dirname "$target")"
    cp -a "$target" "$BACKUP_DIR$target"
  fi
}

install_file() {
  local src="$1"
  local dst="$2"
  backup_if_exists "$dst"
  mkdir -p "$(dirname "$dst")"
  cp -a "$src" "$dst"
}

need_root
mkdir -p "$BACKUP_DIR"

echo "== EMS V3 deploy install =="
echo "Bundle root : $ROOT"
echo "Backup dir  : $BACKUP_DIR"

# Copy config and script files
while IFS= read -r rel; do
  src="$ROOT/$rel"
  dst="/${rel#files/}"
  if [ -f "$src" ]; then
    install_file "$src" "$dst"
  fi
done < <(find "$FILES_DIR" -type f | sed "s#^$ROOT/##" | sort)

# Ensure executable bits on scripts
chmod +x   /etc/profile.d/ems_network_status.sh   /root/kinetics-grid-ems/ems_boot_v3/scripts/*.sh   /root/kinetics-grid-ems/ems_network_bootup/nb_ems_gateway_start.sh   /root/kinetics-grid-ems/ems_network_bootup/nb_ems_gateway_status.sh   /root/kinetics-grid-ems/ems_network_bootup/profile/ems_network_status.sh

# Disable old conflicting units if present
systemctl disable nb-ems-gateway.service 2>/dev/null || true
systemctl stop nb-ems-gateway.service 2>/dev/null || true
systemctl disable ems-network-setup.service 2>/dev/null || true
systemctl stop ems-network-setup.service 2>/dev/null || true
systemctl reset-failed nb-ems-gateway.service 2>/dev/null || true
systemctl reset-failed ems-network-setup.service 2>/dev/null || true

# Use app-stack target to bring app layer up on boot
systemctl daemon-reload
systemctl disable ems-v3-gateway.service ems-v3-soc-controller.service 2>/dev/null || true
systemctl enable ems-v3-eth1.service ems-v3-wifi.service cloudflared.service ems-v3-solis-link.service ems-v3-app-stack.target

# Show status summary
cat <<'EOM'

Install complete.

Next recommended steps:
  1. Verify repo/codebase exists under /root/kinetics-grid-ems
  2. Run post_install_check.sh
  3. Reboot the unit

Manual commands:
  systemctl list-dependencies ems-v3-app-stack.target
  systemctl status ems-v3-eth1.service --no-pager -l
  systemctl status ems-v3-wifi.service --no-pager -l
  systemctl status cloudflared.service --no-pager -l
  systemctl status ems-v3-solis-link.service --no-pager -l
  systemctl status ems-v3-gateway.service --no-pager -l
  systemctl status ems-v3-soc-controller.service --no-pager -l
EOM
