#!/bin/sh
# Install unit only; does NOT enable/start Central Sync or change networking.
set -eu
GATEWAY_ROOT="${1:-/opt/ornate-ems-gateway/backend}"
CONFIG_ROOT=/etc/ornate-ems-gateway
[ -f "$GATEWAY_ROOT/app/central_sync/service.py" ] || { echo "Central Sync source not found" >&2; exit 2; }
mkdir -p "$CONFIG_ROOT" /var/lib/ornate-central-sync
if [ ! -f "$CONFIG_ROOT/central_sync.json" ]; then
  cp "$GATEWAY_ROOT/configs/central_sync_frozen_v1_3_kalpa.json" "$CONFIG_ROOT/central_sync.json"
  chmod 600 "$CONFIG_ROOT/central_sync.json"
fi
install -m 0644 "$GATEWAY_ROOT/deployment/ornate-central-sync.service" /etc/systemd/system/ornate-central-sync.service
systemctl daemon-reload
printf '%s\n' 'Central Sync unit installed, but NOT enabled or started; config remains disabled.'
