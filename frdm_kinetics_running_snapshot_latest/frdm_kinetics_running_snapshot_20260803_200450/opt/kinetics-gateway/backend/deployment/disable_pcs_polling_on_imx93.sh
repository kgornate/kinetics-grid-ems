#!/bin/sh
set -eu
CONFIG=/etc/kinetics-gateway/config.json
VENV=/opt/kinetics-gateway/venv
STAMP=$(date +%Y%m%d_%H%M%S)
cp -p "$CONFIG" "$CONFIG.before_disable_pcs_$STAMP"
"$VENV/bin/python" - "$CONFIG" <<'PY'
import json, os, sys, tempfile
path=sys.argv[1]
config=json.load(open(path,encoding='utf-8'))
config.setdefault('pcs', {})['enabled']=False
config['pcs']['write_enabled']=False
fd,tmp=tempfile.mkstemp(prefix='config.json.',dir=os.path.dirname(path),text=True)
with os.fdopen(fd,'w',encoding='utf-8') as f:
    json.dump(config,f,indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
os.replace(tmp,path)
PY
systemctl restart kinetics-gateway.service
sleep 5
systemctl --no-pager --full status kinetics-gateway.service || true
echo "PCS polling disabled; BMS and gateway remain active."
