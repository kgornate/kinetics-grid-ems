from __future__ import annotations
from typing import Any
SEVERITY_ORDER={'debug':10,'info':20,'warning':30,'error':40,'critical':50}
class EventLogger:
    def __init__(self, storage: Any|None, min_severity: str='debug', enabled: bool=True) -> None:
        self.storage=storage; self.min_severity=min_severity.lower(); self.enabled=enabled
    def log(self,severity:str,event_type:str,message:str,payload:dict[str,Any]|None=None,*,source:str|None=None,asset_id:str|None=None):
        if not self.enabled or not self.storage: return None
        sev=severity.lower()
        if SEVERITY_ORDER.get(sev,20) < SEVERITY_ORDER.get(self.min_severity,10): return None
        return self.storage.insert_event(sev,event_type,message,payload or {},source=source,asset_id=asset_id)
    def debug(self,*a,**kw): return self.log('debug',*a,**kw)
    def info(self,*a,**kw): return self.log('info',*a,**kw)
    def warning(self,*a,**kw): return self.log('warning',*a,**kw)
    def error(self,*a,**kw): return self.log('error',*a,**kw)
    def critical(self,*a,**kw): return self.log('critical',*a,**kw)
