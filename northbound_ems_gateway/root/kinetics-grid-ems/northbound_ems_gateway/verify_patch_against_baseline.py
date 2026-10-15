#!/usr/bin/env python3
"""Read-only baseline SHA/point-map verifier. Never writes to the gateway."""
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
B=Path(__file__).resolve().parent

def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()

def check(root):
    audit=json.loads((B/'audit.json').read_text())
    for rel,hashes in audit['files'].items():
        assert sha(root/rel)==hashes['old_sha256'],f'Baseline differs: {rel}'
        assert sha(B/'patch_files'/rel)==hashes['new_sha256'],f'Patch corrupted: {rel}'
    rel='data/central_sync/canonical_signal_policy_frozen_v1_1.json'
    old=json.loads((root/rel).read_text())
    new=json.loads((B/'patch_files'/rel).read_text())
    assert len(old['signals'])==len(new['signals'])==1422
    old_map={x['point_id']:x for x in old['signals']}
    new_map={x['point_id']:x for x in new['signals']}
    assert old_map.keys()==new_map.keys()
    n=0
    for k,v in old_map.items():
        nv=new_map[k]
        if v['primary_stream']!='S2 general_asset_telemetry':
            assert v==nv,f'Unexpected non-S2 policy change: {k}'
        else:
            n+=1
            assert all(v.get(key)==nv.get(key) for key in set(v)|set(nv) if key not in ('policy','central_record_sec','trigger_upload_rule')),(k,'identity field changed')
    assert n==1350
    assert new['s2_policy_counts_canonical']=={'ON_CHANGE_HEARTBEAT':732,'PERIODIC':618}
    assert old['counts']==new['counts']
    print('PASS: baseline hashes; patched hashes; S2 point counts and metadata; 72 other canonical points unchanged')
    print('Read-only verification. No gateway files modified.')

if __name__=='__main__':
    if len(sys.argv)!=2:
        sys.exit('Usage: python3 verify_patch_against_baseline.py /path/to/offline_oct9_gateway_root')
    try: check(Path(sys.argv[1]))
    except Exception as exc: sys.exit('STOP: '+str(exc))
