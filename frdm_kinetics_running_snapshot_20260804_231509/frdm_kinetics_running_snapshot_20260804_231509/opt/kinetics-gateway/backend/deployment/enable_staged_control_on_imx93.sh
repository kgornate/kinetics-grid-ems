#!/bin/sh
set -eu

if [ "${1:-}" != "ENABLE_STAGE_WRITES" ]; then
  echo "Refusing to arm hardware writes."
  echo "Run: sh $0 ENABLE_STAGE_WRITES"
  exit 2
fi

CONFIG=/etc/kinetics-gateway/config.json
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP="${CONFIG}.before_staged_control_${STAMP}"
cp -a "$CONFIG" "$BACKUP"

python3 - "$CONFIG" <<'PY'
import json, sys
from pathlib import Path
p=Path(sys.argv[1])
c=json.loads(p.read_text())
pcs=c.get('pcs', {})
if not pcs.get('enabled'):
    raise SystemExit('PCS must already be enabled before staged control is armed')
if pcs.get('transport') != 'rtu':
    raise SystemExit('PCS transport must be rtu')
devices=pcs.get('devices') or []
pcs1=next((d for d in devices if d.get('asset_id')=='pcs_1'), None)
if not pcs1 or not pcs1.get('enabled') or int(pcs1.get('unit_id',0)) != 1:
    raise SystemExit('pcs_1 slave ID 1 must be enabled')
serial=pcs.get('serial') or {}
if int(serial.get('baudrate',0)) != 38400 or int(serial.get('bytesize',0)) != 8 or serial.get('parity') != 'N' or int(serial.get('stopbits',0)) != 1:
    raise SystemExit('PCS serial configuration must be confirmed 38400 8N1')

c['mode']='control_enabled'
c.setdefault('bms', {})['write_enabled']=True
c.setdefault('pcs', {})['write_enabled']=True
control=c.setdefault('control_sequence', {})
control['enabled']=True
control['allow_full_automatic_sequence']=False
control.setdefault('confirmation_phrase','EXECUTE_STAGE_WRITE')
control.setdefault('pairs',[
  {'pair_id':'pair_1','rack_id':1,'pcs_asset_id':'pcs_1','enabled':True},
  {'pair_id':'pair_2','rack_id':2,'pcs_asset_id':'pcs_2','enabled':False},
  {'pair_id':'pair_3','rack_id':3,'pcs_asset_id':'pcs_3','enabled':False},
  {'pair_id':'pair_4','rack_id':4,'pcs_asset_id':'pcs_4','enabled':False},
])
control.setdefault('bms_rack_voltage_min_v',1100.0)
control.setdefault('bms_rack_voltage_max_v',1500.0)
control.setdefault('pcs_dc_bus_voltage_min_v',1100.0)
control.setdefault('pcs_dc_bus_voltage_max_v',1500.0)
control.setdefault('max_abs_power_kw',240.0)
control.setdefault('minimum_bms_current_limit_a',0.1)
control.setdefault('enforce_dynamic_bms_power_limit',True)
control.setdefault('valid_samples_required',3)
control.setdefault('sample_interval_seconds',0.5)
control.setdefault('contactor_close_timeout_seconds',10.0)
control.setdefault('pcs_start_timeout_seconds',10.0)
control.setdefault('require_positive_and_negative_contactors',True)
control.setdefault('require_precharge_success',True)
p.write_text(json.dumps(c,indent=2,ensure_ascii=False)+'\n')
print('Staged control armed; full automatic sequence remains disabled.')
print('Pair 1: BMS Rack 1 <-> PCS 1')
print('Safety cap: 240 kW; voltage window: 1100-1500 V')
PY

systemctl restart kinetics-gateway.service
sleep 5
systemctl status kinetics-gateway.service --no-pager -l

echo "Config backup: $BACKUP"
echo "No hardware command has been sent. Stage writes require API confirmation EXECUTE_STAGE_WRITE."
