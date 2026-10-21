#!/bin/sh
# Fresh FRDM-i.MX93 Kalpa DEV deployment (local mock/read-only).
# No IP changes, no network service changes, and NO automatic service startup.
set -eu
SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TARGET=/opt/ornate-ems-gateway
APP="$TARGET/backend"
CONF=/etc/ornate-ems-gateway
[ -f "$SOURCE_DIR/app/main.py" ] || { echo 'Invalid source folder' >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo 'python3 missing from Yocto image' >&2; exit 2; }
python3 -m venv --help >/dev/null 2>&1 || { echo 'python3 venv missing; do not continue until BSP is fixed' >&2; exit 2; }
mkdir -p "$TARGET" "$CONF" /mnt/ems-logs/ornate-ems-gateway
if [ -e "$APP" ]; then
  echo "$APP already exists. First-install script refuses to overwrite it." >&2
  exit 3
fi
# Copy only source; do not touch Cloudflare, SSH, Weston, Wi-Fi or Ethernet configs.
cp -a "$SOURCE_DIR" "$APP"
python3 -m venv "$TARGET/venv"
"$TARGET/venv/bin/python" -m pip --version >/dev/null 2>&1 || { echo 'venv pip missing; Yocto image needs Python pip/ensurepip support' >&2; exit 4; }
"$TARGET/venv/bin/python" -m pip install -r "$APP/requirements.txt"
# Local development config uses real Lineage/Elecod schema and four-pair mocks.
# Positively disable all write/control gates while no hardware is connected.
python3 - "$APP/configs/elecod_lineage_4pair_sil.json" "$CONF/config.json" <<'PYCONFIG'
import json, sys
from pathlib import Path
source, dest = (Path(p) for p in sys.argv[1:])
if dest.exists():
    print('Refusing to overwrite existing config:', dest)
else:
    obj=json.loads(source.read_text(encoding='utf-8'))
    if obj.get('mode')!='mock': raise SystemExit('SIL template is not mock mode')
    obj['bms']['write_enabled']=False
    obj['pcs']['write_enabled']=False
    obj.setdefault('control_sequence',{})['enabled']=False
    obj['control_sequence']['allow_full_automatic_sequence']=False
    obj['api_host']='127.0.0.1'
    dest.write_text(json.dumps(obj, indent=2)+'\n', encoding='utf-8')
    dest.chmod(0o600)
    print('Created safe read-only mock config:', dest)
PYCONFIG
# Random development credentials, never use weak stock passwords.
if [ ! -f "$CONF/ornate-ems-gateway.env" ]; then
  python3 - "$CONF/ornate-ems-gateway.env" <<'PYSECRETS'
import secrets, sys
from pathlib import Path
p=Path(sys.argv[1])
p.write_text('ORNATE_EMS_JWT_SECRET='+secrets.token_urlsafe(48)+'\n'
             'ORNATE_EMS_INTERNAL_PASSWORD='+secrets.token_urlsafe(20)+'\n'
             'ORNATE_EMS_CUSTOMER_PASSWORD='+secrets.token_urlsafe(20)+'\n', encoding='utf-8')
p.chmod(0o600)
print('Created randomized gateway credentials:', p)
PYSECRETS
fi
install -m 0644 "$APP/deployment/ornate-ems-gateway.service" /etc/systemd/system/ornate-ems-gateway.service
systemctl daemon-reload
printf '%s\n' 'Source and dependencies installed. Gateway unit exists but is NOT started/enabled.'
printf '%s\n' 'Before starting, inspect /etc/ornate-ems-gateway/config.json and env file.'
printf '%s\n' 'Start manually: systemctl start ornate-ems-gateway.service'
