#!/bin/sh
set -eu

. /etc/ems_boot_v3.conf

LOG="/var/log/ems_v3_solis_link.log"
LINK="${SOLIS_RTU_LINK:-/dev/ems_solis_rtu}"
CFG_PORT="${SOLIS_RTU_PORT:-/dev/ttyUSB0}"

mkdir -p /var/log
touch "$LOG"

log() {
    echo "$(date) [solis-v3] $*" | tee -a "$LOG"
}

if [ "${SOLIS_RTU_ENABLED:-0}" != "1" ]; then
    log "Solis RTU disabled in config"
    exit 0
fi

log "======================================"
log "EMS V3 Solis USB link setup started"
log "Configured port : $CFG_PORT"
log "Stable link     : $LINK"

TARGET=""

i=1
while [ "$i" -le 20 ]; do
    if [ -e "$CFG_PORT" ]; then
        TARGET="$CFG_PORT"
        break
    fi

    if ls /dev/serial/by-id/* >/dev/null 2>&1; then
        TARGET="$(ls -1 /dev/serial/by-id/* | head -n 1)"
        break
    fi

    if ls /dev/ttyUSB* >/dev/null 2>&1; then
        TARGET="$(ls -1 /dev/ttyUSB* | head -n 1)"
        break
    fi

    log "waiting for Solis USB serial device ($i/20)"
    sleep 2
    i=$((i+1))
done

if [ -z "$TARGET" ]; then
    log "No Solis USB serial device found"
    exit 1
fi

REAL_TARGET="$(readlink -f "$TARGET")"
ln -sfn "$REAL_TARGET" "$LINK"

log "Selected target : $TARGET"
log "Resolved target : $REAL_TARGET"
log "Created link    : $LINK -> $REAL_TARGET"

ls -l "$LINK" | tee -a "$LOG" || true
ls -l /dev/ttyUSB* 2>/dev/null | tee -a "$LOG" || true
ls -l /dev/serial/by-id 2>/dev/null | tee -a "$LOG" || true

log "EMS V3 Solis USB link setup completed"
log "======================================"
