#!/bin/sh
# ==========================================================
# NorthBound EMS Gateway startup wrapper
# Runs after ems-network-setup.service.
# Prints boot-time diagnostics to journal+console and writes wrapper log.
# ==========================================================

set -u

CONFIG_FILE="/etc/nb_ems_gateway.conf"
if [ -f "$CONFIG_FILE" ]; then
    . "$CONFIG_FILE"
fi

NB_EMS_GATEWAY_DIR="${NB_EMS_GATEWAY_DIR:-/root/kinetics-grid-ems/northbound_ems_gateway}"
NB_EMS_GATEWAY_PYTHON="${NB_EMS_GATEWAY_PYTHON:-/usr/bin/python3}"
NB_EMS_GATEWAY_CONFIG="${NB_EMS_GATEWAY_CONFIG:-configs/development.json}"
NB_EMS_GATEWAY_MOCK="${NB_EMS_GATEWAY_MOCK:-1}"
NB_EMS_GATEWAY_API_PORT="${NB_EMS_GATEWAY_API_PORT:-8000}"
NB_EMS_GATEWAY_EXTRA_ARGS="${NB_EMS_GATEWAY_EXTRA_ARGS:-}"
NB_EMS_GATEWAY_START_LOG="${NB_EMS_GATEWAY_START_LOG:-/var/log/nb_ems_gateway_start.log}"

mkdir -p "$(dirname "$NB_EMS_GATEWAY_START_LOG")"

log() {
    LINE="$(date '+%Y-%m-%d %H:%M:%S') $*"
    echo "$LINE"
    echo "$LINE" >> "$NB_EMS_GATEWAY_START_LOG"
}

log "======================================"
log "NorthBound EMS Gateway boot startup"
log "======================================"
log "Working directory : $NB_EMS_GATEWAY_DIR"
log "Python            : $NB_EMS_GATEWAY_PYTHON"
log "Config            : $NB_EMS_GATEWAY_CONFIG"
log "Mock mode         : $NB_EMS_GATEWAY_MOCK"
log "Expected API port : $NB_EMS_GATEWAY_API_PORT"

log "Checking network service state..."
if command -v systemctl >/dev/null 2>&1; then
    systemctl is-active ems-network-setup.service 2>&1 | while IFS= read -r L; do log "ems-network-setup.service: $L"; done || true
fi

log "Default internet route:"
ip route get 1.1.1.1 2>&1 | while IFS= read -r L; do log "$L"; done || true

log "Interface summary:"
ip -br addr show eth0 2>&1 | while IFS= read -r L; do log "$L"; done || true
ip -br addr show eth1 2>&1 | while IFS= read -r L; do log "$L"; done || true
ip -br addr show mlan0 2>&1 | while IFS= read -r L; do log "$L"; done || true

if [ ! -d "$NB_EMS_GATEWAY_DIR" ]; then
    log "ERROR: gateway directory does not exist: $NB_EMS_GATEWAY_DIR"
    exit 1
fi

if [ ! -f "$NB_EMS_GATEWAY_DIR/src/nb_ems_gateway/main.py" ]; then
    log "ERROR: gateway Python package not found under: $NB_EMS_GATEWAY_DIR/src/nb_ems_gateway"
    exit 1
fi

if [ ! -f "$NB_EMS_GATEWAY_DIR/$NB_EMS_GATEWAY_CONFIG" ]; then
    log "ERROR: gateway config does not exist: $NB_EMS_GATEWAY_DIR/$NB_EMS_GATEWAY_CONFIG"
    exit 1
fi

if [ ! -x "$NB_EMS_GATEWAY_PYTHON" ]; then
    log "ERROR: Python executable not found or not executable: $NB_EMS_GATEWAY_PYTHON"
    exit 1
fi

log "Checking if port $NB_EMS_GATEWAY_API_PORT is already used before starting..."
ss -lntp 2>/dev/null | grep ":$NB_EMS_GATEWAY_API_PORT" | while IFS= read -r L; do log "$L"; done || true

cd "$NB_EMS_GATEWAY_DIR"
export PYTHONPATH="$NB_EMS_GATEWAY_DIR/src"
export PYTHONUNBUFFERED="1"

CMD="$NB_EMS_GATEWAY_PYTHON -m nb_ems_gateway.main --config $NB_EMS_GATEWAY_CONFIG"
if [ "$NB_EMS_GATEWAY_MOCK" = "1" ]; then
    CMD="$CMD --mock"
fi
if [ -n "$NB_EMS_GATEWAY_EXTRA_ARGS" ]; then
    CMD="$CMD $NB_EMS_GATEWAY_EXTRA_ARGS"
fi

log "Starting command: $CMD"
log "Gateway process output will continue in journal and console."
log "======================================"

# shellcheck disable=SC2086
exec $CMD
