from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from nb_ems_gateway.dictionary.register_map import RegisterMap, RegisterPoint
class AssetManager:
    def __init__(self, register_map: RegisterMap) -> None:
        self.register_map=register_map
        self.telemetry={a['asset_id']:{'asset_id':a['asset_id'],'display_name':a.get('display_name',a['asset_id']),'online':False,'last_update_utc':None,'signal_count':0,'bad_signal_count':0,'signals':{},'key_signals':{}} for a in register_map.assets}
    def update_signal(self, point:RegisterPoint, value:float|None, quality:str='good', raw_registers:list[int]|None=None, error:str|None=None)->None:
        asset=self.telemetry.setdefault(point.asset_id,{'asset_id':point.asset_id,'display_name':point.asset_display_name,'online':False,'signals':{},'key_signals':{}})
        sig={'name':point.signal_name,'display_name':point.point_name,'value':value,'unit':point.unit,'category':point.category,'quality':quality,'address':point.address,'raw_registers':raw_registers or [],'description':point.description,'updated_utc':datetime.now(timezone.utc).isoformat()}
        if error: sig['error']=error
        asset['signals'][point.signal_name]=sig
        if point.key_signal: asset['key_signals'][point.signal_name]=sig
        asset['online']=True; asset['last_update_utc']=sig['updated_utc']; asset['signal_count']=len(asset['signals']); asset['bad_signal_count']=sum(1 for s in asset['signals'].values() if s.get('quality')!='good')
    def snapshot(self, *, asset_id: str|None=None, category: str|None=None, key_only: bool=False) -> dict[str,Any]:
        ids=[asset_id] if asset_id else sorted(self.telemetry)
        out={}
        for aid in ids:
            if aid not in self.telemetry: continue
            asset=self.telemetry[aid]; signals=asset['key_signals'] if key_only else asset['signals']
            if category: signals={k:v for k,v in signals.items() if v.get('category')==category}
            item={k:v for k,v in asset.items() if k not in ['signals','key_signals']}; item['signals']=signals; item['key_signals']=asset['key_signals']; out[aid]=item
        return out
    def asset_list(self)->list[dict[str,Any]]:
        return [{'asset_id':aid,'display_name':a.get('display_name',aid),'online':a.get('online',False),'signal_count':a.get('signal_count',0),'bad_signal_count':a.get('bad_signal_count',0),'last_update_utc':a.get('last_update_utc')} for aid,a in sorted(self.telemetry.items())]
