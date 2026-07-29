#!/bin/bash
set -euo pipefail

ARCHIVE="/root/kinetics_gateway_latest_running.tar.gz"
META="/root/kinetics_gateway_snapshot_meta"

echo "Creating gateway snapshot..."

rm -rf "$META"
rm -f "$ARCHIVE"
mkdir -p "$META"

# Basic identification
date -Is > "$META/captured_at.txt"
hostname > "$META/hostname.txt"
uname -a > "$META/uname.txt"

if [ -f /etc/os-release ]; then
    cp -a /etc/os-release "$META/os-release.txt"
fi

# Gateway service definition and runtime state
systemctl cat kinetics-gateway.service \
    > "$META/kinetics-gateway.service.txt" 2>&1 || true

systemctl show kinetics-gateway.service \
    -p FragmentPath \
    -p ExecStart \
    -p Environment \
    -p ActiveState \
    -p SubState \
    -p MainPID \
    -p NRestarts \
    -p MemoryCurrent \
    -p MemoryPeak \
    -p ActiveEnterTimestamp \
    > "$META/kinetics-gateway.runtime.txt" 2>&1 || true

# Cloudflare tunnel definition and state
systemctl cat cloudflared.service \
    > "$META/cloudflared.service.txt" 2>&1 || true

systemctl show cloudflared.service \
    -p FragmentPath \
    -p ExecStart \
    -p ActiveState \
    -p SubState \
    -p MainPID \
    -p NRestarts \
    > "$META/cloudflared.runtime.txt" 2>&1 || true

# Current running processes
ps -ef > "$META/processes.txt"

# Python version and installed packages
if [ -x /opt/kinetics-gateway/venv/bin/python ]; then
    /opt/kinetics-gateway/venv/bin/python --version \
        > "$META/python-version.txt" 2>&1

    /opt/kinetics-gateway/venv/bin/python -m pip freeze \
        > "$META/pip-freeze.txt" 2>&1
fi

# Recent gateway logs, including the memory/OOM-related period
journalctl -u kinetics-gateway.service \
    -n 2000 \
    --no-pager \
    > "$META/kinetics-gateway-journal-last-2000.txt" 2>&1 || true

journalctl -u cloudflared.service \
    -n 500 \
    --no-pager \
    > "$META/cloudflared-journal-last-500.txt" 2>&1 || true

# Kernel OOM evidence
journalctl -k \
    --no-pager \
    | grep -Ei "oom|out of memory|killed process" \
    > "$META/kernel-oom-events.txt" 2>&1 || true

# Record the actual systemd unit file locations
systemctl show kinetics-gateway.service \
    -p FragmentPath \
    --value \
    > "$META/kinetics-gateway-service-path.txt" 2>/dev/null || true

systemctl show cloudflared.service \
    -p FragmentPath \
    --value \
    > "$META/cloudflared-service-path.txt" 2>/dev/null || true

FILES=(
    "/opt/kinetics-gateway"
    "/etc/kinetics-gateway"
    "$META"
)

# Include actual systemd unit files
KINETICS_SERVICE_PATH="$(
    systemctl show kinetics-gateway.service -p FragmentPath --value 2>/dev/null || true
)"

CLOUDFLARED_SERVICE_PATH="$(
    systemctl show cloudflared.service -p FragmentPath --value 2>/dev/null || true
)"

if [ -n "$KINETICS_SERVICE_PATH" ] && [ -e "$KINETICS_SERVICE_PATH" ]; then
    FILES+=("$KINETICS_SERVICE_PATH")
fi

if [ -n "$CLOUDFLARED_SERVICE_PATH" ] && [ -e "$CLOUDFLARED_SERVICE_PATH" ]; then
    FILES+=("$CLOUDFLARED_SERVICE_PATH")
fi

# Include Cloudflare routing configuration
if [ -d /etc/cloudflared ]; then
    FILES+=("/etc/cloudflared")
fi

# Include useful gateway scripts when present
for FILE in \
    /root/ems_safe_stop_all.sh \
    /root/monitor_all_pairs_cached.sh \
    /etc/ems_boot_v3.conf
do
    if [ -e "$FILE" ]; then
        FILES+=("$FILE")
    fi
done

# Create the archive.
# The Python virtual environment is excluded; pip-freeze captures dependencies.
tar \
    --exclude='opt/kinetics-gateway/venv' \
    --exclude='opt/kinetics-gateway/venv/*' \
    --exclude='*/__pycache__' \
    --exclude='*/__pycache__/*' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='*.db-wal' \
    --exclude='*.db-shm' \
    -czf "$ARCHIVE" \
    "${FILES[@]}"

echo
echo "Archive created:"
ls -lh "$ARCHIVE"

echo
echo "SHA-256:"
sha256sum "$ARCHIVE"
