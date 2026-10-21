#!/bin/sh
set -eu
CONFIG=/etc/kinetics-gateway/config.json
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP="${CONFIG}.before_disable_staged_control_${STAMP}"
cp -a "$CONFIG" "$BACKUP"
python3 - "$CONFIG" <<'PY'
import json, sys
from pathlib import Path
p=Path(sys.argv[1])
c=json.loads(p.read_text())
c['mode']='read_only'
c.setdefault('bms', {})['write_enabled']=False
c.setdefault('pcs', {})['write_enabled']=False
c.setdefault('control_sequence', {})['enabled']=False
c['control_sequence']['allow_full_automatic_sequence']=False
p.write_text(json.dumps(c,indent=2,ensure_ascii=False)+'\n')
print('Staged control disabled; gateway returned to read_only.')
PY
systemctl restart kinetics-gateway.service
sleep 5
systemctl status kinetics-gateway.service --no-pager -l
echo "Config backup: $BACKUP"
