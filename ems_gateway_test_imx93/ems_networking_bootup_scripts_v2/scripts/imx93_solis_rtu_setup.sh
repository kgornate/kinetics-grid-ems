#!/bin/sh
# ==========================================================
# i.MX93 Solis Inverter Modbus RTU Setup
# Purpose:
#   - wait for USB-RS485 adapter
#   - configure serial port as 9600 8N1 raw mode
#   - create stable symlink /dev/ems_solis_rtu
#   - optionally patch SOC + Solis gateway JSON config to use stable link
#   - optionally run a read-only Modbus RTU probe
# ==========================================================

set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/ems_common.sh"
load_config

SOLIS_RTU_ENABLED="${SOLIS_RTU_ENABLED:-0}"
SOLIS_RTU_PORT="${SOLIS_RTU_PORT:-/dev/ttyUSB1}"
SOLIS_RTU_STABLE_LINK="${SOLIS_RTU_STABLE_LINK:-/dev/ems_solis_rtu}"
SOLIS_RTU_BAUDRATE="${SOLIS_RTU_BAUDRATE:-9600}"
SOLIS_RTU_DATABITS="${SOLIS_RTU_DATABITS:-8}"
SOLIS_RTU_PARITY="${SOLIS_RTU_PARITY:-N}"
SOLIS_RTU_STOPBITS="${SOLIS_RTU_STOPBITS:-1}"
SOLIS_RTU_UNIT_ID="${SOLIS_RTU_UNIT_ID:-1}"
SOLIS_RTU_TIMEOUT_SEC="${SOLIS_RTU_TIMEOUT_SEC:-3}"
SOLIS_RTU_WAIT_ATTEMPTS="${SOLIS_RTU_WAIT_ATTEMPTS:-20}"
SOLIS_RTU_WAIT_SLEEP_SEC="${SOLIS_RTU_WAIT_SLEEP_SEC:-1}"
SOLIS_RTU_REQUIRED="${SOLIS_RTU_REQUIRED:-0}"
SOLIS_RTU_BOOT_READ_TEST="${SOLIS_RTU_BOOT_READ_TEST:-0}"
SOLIS_RTU_CONTROL_METHOD="${SOLIS_RTU_CONTROL_METHOD:-holding_onoff_3007}"
SOLIS_RTU_PATCH_GATEWAY_CONFIG="${SOLIS_RTU_PATCH_GATEWAY_CONFIG:-1}"
SOC_SOLIS_GATEWAY_CONFIG="${SOC_SOLIS_GATEWAY_CONFIG:-/root/kinetics-grid-ems/northbound_ems_gateway/configs/soc_solis_field_rtu.json}"

cat <<EOM
======================================
i.MX93 Solis Modbus RTU Setup
======================================
Enabled       : $SOLIS_RTU_ENABLED
Configured dev: $SOLIS_RTU_PORT
Stable link   : $SOLIS_RTU_STABLE_LINK
Baud / format : ${SOLIS_RTU_BAUDRATE} ${SOLIS_RTU_DATABITS}${SOLIS_RTU_PARITY}${SOLIS_RTU_STOPBITS}
Unit ID       : $SOLIS_RTU_UNIT_ID
Required      : $SOLIS_RTU_REQUIRED
Boot read test: $SOLIS_RTU_BOOT_READ_TEST
Gateway config: $SOC_SOLIS_GATEWAY_CONFIG
======================================
EOM

if [ "$SOLIS_RTU_ENABLED" != "1" ]; then
    echo "Solis RTU setup disabled by config."
    exit 0
fi

# Load common USB serial drivers. Missing modules are normal on some images.
for MOD in usbserial ch341 cp210x ftdi_sio pl2303; do
    modprobe "$MOD" 2>/dev/null || true
done

choose_auto_port() {
    for CANDIDATE in /dev/ttyUSB* /dev/ttyACM*; do
        [ -c "$CANDIDATE" ] && { echo "$CANDIDATE"; return 0; }
    done
    return 1
}

wait_for_port() {
    WANTED="$1"
    i=1
    while [ "$i" -le "$SOLIS_RTU_WAIT_ATTEMPTS" ]; do
        if [ "$WANTED" = "auto" ]; then
            AUTO_PORT="$(choose_auto_port 2>/dev/null || true)"
            if [ -n "$AUTO_PORT" ]; then
                echo "$AUTO_PORT"
                return 0
            fi
        else
            if [ -c "$WANTED" ]; then
                echo "$WANTED"
                return 0
            fi
        fi
        echo "[solis-rtu] Waiting for $WANTED attempt $i/$SOLIS_RTU_WAIT_ATTEMPTS" >&2
        sleep "$SOLIS_RTU_WAIT_SLEEP_SEC"
        i=$((i + 1))
    done
    return 1
}

SOLIS_REAL_PORT="$(wait_for_port "$SOLIS_RTU_PORT" 2>/tmp/solis_rtu_wait.log || true)"
cat /tmp/solis_rtu_wait.log 2>/dev/null || true
rm -f /tmp/solis_rtu_wait.log

if [ -z "$SOLIS_REAL_PORT" ]; then
    echo "ERROR: Solis RTU serial port not found. Configured: $SOLIS_RTU_PORT"
    echo "Available serial devices:"
    ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || true
    if [ "$SOLIS_RTU_REQUIRED" = "1" ]; then
        exit 1
    fi
    exit 0
fi

if command -v readlink >/dev/null 2>&1; then
    SOLIS_REAL_PORT="$(readlink -f "$SOLIS_REAL_PORT" 2>/dev/null || echo "$SOLIS_REAL_PORT")"
fi

echo "[solis-rtu] Selected port: $SOLIS_REAL_PORT"

# Create stable runtime symlink. This avoids gateway config depending on /dev/ttyUSB numbering.
rm -f "$SOLIS_RTU_STABLE_LINK" 2>/dev/null || true
ln -s "$SOLIS_REAL_PORT" "$SOLIS_RTU_STABLE_LINK"
chmod 666 "$SOLIS_REAL_PORT" 2>/dev/null || true

# Configure raw serial mode. Keep this non-fatal because pyserial also sets parameters.
STTY_ARGS="$SOLIS_RTU_BAUDRATE cs$SOLIS_RTU_DATABITS raw -echo -ixon -ixoff -crtscts"
if [ "$SOLIS_RTU_PARITY" = "N" ]; then
    STTY_ARGS="$STTY_ARGS -parenb"
elif [ "$SOLIS_RTU_PARITY" = "E" ]; then
    STTY_ARGS="$STTY_ARGS parenb -parodd"
elif [ "$SOLIS_RTU_PARITY" = "O" ]; then
    STTY_ARGS="$STTY_ARGS parenb parodd"
fi
if [ "$SOLIS_RTU_STOPBITS" = "1" ]; then
    STTY_ARGS="$STTY_ARGS -cstopb"
else
    STTY_ARGS="$STTY_ARGS cstopb"
fi

stty -F "$SOLIS_REAL_PORT" $STTY_ARGS 2>/dev/null || true

echo "[solis-rtu] Stable link:"
ls -l "$SOLIS_RTU_STABLE_LINK" || true

echo "[solis-rtu] Serial settings:"
stty -F "$SOLIS_REAL_PORT" -a 2>/dev/null || true

# Patch SOC + Solis controller config if the v1.7 gateway codebase is present.
if [ "$SOLIS_RTU_PATCH_GATEWAY_CONFIG" = "1" ]; then
    if [ -f "$SOC_SOLIS_GATEWAY_CONFIG" ] && command -v python3 >/dev/null 2>&1; then
        echo "[solis-rtu] Patching gateway Solis config: $SOC_SOLIS_GATEWAY_CONFIG"
        python3 - "$SOC_SOLIS_GATEWAY_CONFIG" <<PY
import json, sys
path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)
solis = data.setdefault('solis', {})
solis['enabled'] = True
solis['transport'] = 'rtu'
solis['serial_port'] = '$SOLIS_RTU_STABLE_LINK'
solis['baudrate'] = int('$SOLIS_RTU_BAUDRATE')
solis['unit_id'] = int('$SOLIS_RTU_UNIT_ID')
solis['timeout'] = float('$SOLIS_RTU_TIMEOUT_SEC')
solis['control_method'] = '$SOLIS_RTU_CONTROL_METHOD'
with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
print('patched_solis_serial_port=', solis.get('serial_port'))
PY
    else
        echo "[solis-rtu] Gateway config not found or python3 missing. Skipping config patch."
    fi
fi

if [ "$SOLIS_RTU_BOOT_READ_TEST" = "1" ]; then
    if [ -x "$SCRIPT_DIR/solis_rtu_modbus_check.py" ]; then
        echo "[solis-rtu] Running read-only Solis Modbus RTU probe..."
        if "$SCRIPT_DIR/solis_rtu_modbus_check.py" \
            --port "$SOLIS_RTU_STABLE_LINK" \
            --baudrate "$SOLIS_RTU_BAUDRATE" \
            --unit-id "$SOLIS_RTU_UNIT_ID" \
            --timeout "$SOLIS_RTU_TIMEOUT_SEC"; then
            echo "[solis-rtu] Read-only Modbus probe passed."
        else
            echo "WARNING: Solis Modbus RTU probe failed. Serial setup still completed."
            if [ "$SOLIS_RTU_REQUIRED" = "1" ]; then
                exit 1
            fi
        fi
    else
        echo "[solis-rtu] Probe script not found/executable. Skipping read test."
    fi
fi

echo "======================================"
echo "Solis RTU setup completed"
echo "======================================"
exit 0
