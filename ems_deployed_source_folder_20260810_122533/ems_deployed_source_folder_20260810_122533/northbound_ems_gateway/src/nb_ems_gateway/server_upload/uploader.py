from __future__ import annotations
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
import httpx
from nb_ems_gateway.config.models import ServerUploadConfig
from .interface import get_ipv4_for_interface
from .payload import build_upload_payload
@dataclass
class ServerUploadStatus:
    enabled: bool; transport: str; endpoint_url: str|None; network_interface: str; source_ip: str|None=None; payload_mode: str='key_signals'; upload_interval_sec: float=10.0; queue_size: int=0; success_count: int=0; failure_count: int=0; dropped_count: int=0; last_attempt_utc: str|None=None; last_success_utc: str|None=None; last_error: str|None=None; last_status_code: int|None=None; running: bool=False
    def to_dict(self)->dict[str,Any]: return self.__dict__.copy()
class ServerUploadService:
    def __init__(self, config: ServerUploadConfig, container: Any)->None:
        self.config=config; self.container=container; self._task=None; self._running=False; self._queue=[]
        self.status=ServerUploadStatus(config.enabled,config.transport,config.endpoint_url,config.network_interface,payload_mode=config.payload_mode,upload_interval_sec=config.upload_interval_sec)
    async def start(self)->None:
        if not self.config.enabled:
            self.container.event_logger.info('server_upload_disabled','Server upload disabled by config',source='server_upload'); return
        if not self.config.endpoint_url:
            self.status.last_error='endpoint_url missing'; self.container.event_logger.warning('server_upload_config_error',self.status.last_error,source='server_upload'); return
        self.status.source_ip=self.config.source_ip or get_ipv4_for_interface(self.config.network_interface); self._running=True; self.status.running=True; self._task=asyncio.create_task(self._loop())
        self.container.event_logger.info('server_upload_started',f'Server upload started on {self.config.network_interface}',{'endpoint_url':self._safe_endpoint(),'source_ip':self.status.source_ip},source='server_upload')
    async def stop(self)->None:
        self._running=False; self.status.running=False
        if self._task: self._task.cancel(); await asyncio.gather(self._task, return_exceptions=True)
    async def _loop(self)->None:
        while self._running:
            await self.upload_once(); await asyncio.sleep(max(1.0,self.config.upload_interval_sec))
    async def upload_once(self)->dict[str,Any]:
        if not self.config.enabled: return self.status.to_dict()
        payload=build_upload_payload(self.container,payload_mode=self.config.payload_mode)
        if self.config.buffer_when_offline:
            self._queue.append(payload)
            while len(self._queue)>self.config.max_queue_size: self._queue.pop(0); self.status.dropped_count+=1
            while self._queue:
                if not await self._post(self._queue[0]): break
                self._queue.pop(0)
        else: await self._post(payload)
        self.status.queue_size=len(self._queue); return self.status.to_dict()
    async def _post(self,payload:dict[str,Any])->bool:
        self.status.last_attempt_utc=datetime.now(timezone.utc).isoformat(); self.status.last_error=None; self.status.last_status_code=None
        headers={'Content-Type':'application/json','X-Gateway-ID':self.container.config.gateway.id}
        if self.config.api_key: headers['Authorization']=f'Bearer {self.config.api_key}'
        try:
            transport=httpx.AsyncHTTPTransport(local_address=(self.status.source_ip if self.config.bind_to_interface_source_ip else None), verify=self.config.verify_tls)
            async with httpx.AsyncClient(transport=transport,timeout=self.config.timeout_sec) as client: r=await client.post(self.config.endpoint_url,json=payload,headers=headers)
            self.status.last_status_code=r.status_code
            if 200<=r.status_code<300:
                self.status.success_count+=1; self.status.last_success_utc=datetime.now(timezone.utc).isoformat(); self.container.event_logger.info('server_upload_success',f'Uploaded telemetry to server, status={r.status_code}',{'endpoint_url':self._safe_endpoint()},source='server_upload'); return True
            self.status.failure_count+=1; self.status.last_error=f'HTTP {r.status_code}: {r.text[:200]}'; self.container.event_logger.warning('server_upload_failed',self.status.last_error,{'endpoint_url':self._safe_endpoint()},source='server_upload'); return False
        except Exception as exc:
            self.status.failure_count+=1; self.status.last_error=str(exc); self.container.event_logger.warning('server_upload_failed',str(exc),{'endpoint_url':self._safe_endpoint()},source='server_upload'); return False
    def _safe_endpoint(self)->str|None:
        if not self.config.endpoint_url: return None
        p=urlparse(self.config.endpoint_url); return f'{p.scheme}://{p.netloc}{p.path}'
