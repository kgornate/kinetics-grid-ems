#!/bin/sh
set -eu

CONFIG=/etc/kinetics-gateway/config.json
BACKEND=/opt/kinetics-gateway/backend
VENV=/opt/kinetics-gateway/venv
SERIAL_DEVICE=${PCS_SERIAL_DEVICE:-/dev/ttyUSB0}
UNIT_ID=${PCS1_UNIT_ID:-1}
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP="$CONFIG.before_pcs1_readonly_$STAMP"

if [ ! -e "$SERIAL_DEVICE" ]; then
  echo "Serial device does not exist: $SERIAL_DEVICE" >&2
  exit 1
fi
cp -p "$CONFIG" "$BACKUP"

"$VENV/bin/python" - "$CONFIG" "$SERIAL_DEVICE" "$UNIT_ID" <<'PY'
import json, os, sys, tempfile
path, device, unit_text = sys.argv[1:]
unit_id = int(unit_text)
with open(path, encoding='utf-8') as file:
    config = json.load(file)
config['mode'] = 'read_only'
config['pcs'] = {
    'enabled': True,
    'transport': 'rtu',
    'serial': {
        'device': device,
        'baudrate': 38400,
        'bytesize': 8,
        'parity': 'N',
        'stopbits': 1,
        'inter_request_delay_ms': 50.0,
        'retries': 1,
    },
    'devices': [
        {'asset_id': 'pcs_1', 'unit_id': unit_id, 'enabled': True, 'label': 'PCS 1'},
        {'asset_id': 'pcs_2', 'unit_id': 2, 'enabled': False, 'label': 'PCS 2'},
        {'asset_id': 'pcs_3', 'unit_id': 3, 'enabled': False, 'label': 'PCS 3'},
        {'asset_id': 'pcs_4', 'unit_id': 4, 'enabled': False, 'label': 'PCS 4'},
    ],
    'timeout_seconds': 1.5,
    'address_offset': 0,
    'poll_seconds': 5.0,
    'write_enabled': False,
    'overrides_file': 'configs/pcs_overrides.json',
    'max_registers_per_request': 120,
    'commissioning_status': 'PCS1 hardware validated read-only at 38400 8N1; PCS2-PCS4 disabled pending IDs',
}
directory = os.path.dirname(path)
fd, temporary = tempfile.mkstemp(prefix='config.json.', dir=directory, text=True)
try:
    with os.fdopen(fd, 'w', encoding='utf-8') as file:
        json.dump(config, file, indent=2)
        file.write('\n')
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY

cd "$BACKEND"
KINETICS_CONFIG="$CONFIG" "$VENV/bin/python" - <<'PY'
from app.core.config import load_config
config = load_config('/etc/kinetics-gateway/config.json')
assert config.mode == 'read_only'
assert config.pcs.enabled
assert not config.pcs.write_enabled
assert config.pcs.transport == 'rtu'
print('PCS1 read-only config valid:', config.pcs.serial.device, config.pcs.serial.baudrate, [(d.asset_id, d.unit_id, d.enabled) for d in config.pcs.devices])
PY

systemctl restart kinetics-gateway.service
sleep 8
systemctl --no-pager --full status kinetics-gateway.service || true
echo "PCS1 read-only polling enabled. Config backup: $BACKUP"
