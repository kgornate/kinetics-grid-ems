#!/bin/sh
set -eu

ROOT="${1:-/root/ornate-ems-gateway}"
cd "$ROOT"
mkdir -p /var/lib/ornate-central-sync
mkdir -p /mnt/ems-logs/ornate-ems-gateway/backlog_archives || true
install -m 0644 deployment/ornate-central-sync.service /etc/systemd/system/ornate-central-sync.service
systemctl daemon-reload
printf '%s\n' "Installed ornate-central-sync.service."
printf '%s\n' "Central Sync remains controlled by configs/central_sync_frozen_v1_3_kalpa.json (enabled=false by default)."
printf '%s\n' "Set CENTRAL_SYNC_LOCAL_API_PASSWORD and backend auth credentials in /etc/default/ornate-central-sync before enabling."
