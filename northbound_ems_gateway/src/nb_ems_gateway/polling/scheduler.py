from __future__ import annotations
import asyncio, logging, time
from typing import Any
from nb_ems_gateway.decoding.float_codec import decode_float32
LOGGER=logging.getLogger(__name__)
class PollingScheduler:
    def __init__(self, container: Any, reader: Any)->None:
        self.container=container; self.reader=reader; self._task=None; self._running=False; self.cycle_count=0
    async def start(self)->None:
        if not self.container.config.polling.enabled: return
        self._running=True; self._task=asyncio.create_task(self._loop())
        self.container.event_logger.info('polling_started','Polling scheduler started',{'points':self.container.register_map.point_count},source='polling')
    async def stop(self)->None:
        self._running=False
        if self._task: self._task.cancel(); await asyncio.gather(self._task, return_exceptions=True)
    async def _loop(self)->None:
        while self._running:
            start=time.time(); await self.poll_once(); await asyncio.sleep(max(0.2,self.container.config.polling.default_interval_sec-(time.time()-start)))
    async def poll_once(self)->dict[str,Any]:
        errors=[]; good=0; bad=0
        for p in self.container.register_map.points:
            try:
                regs=self.reader.read_point(p); val=decode_float32(regs,self.container.config.decoding.byte_order)
                if self.container.config.decoding.apply_factor: val*=p.factor
                self.container.asset_manager.update_signal(p,val,'good',regs); good+=1
            except Exception as exc:
                errors.append(f'{p.asset_id}.{p.signal_name}: {exc}'); self.container.asset_manager.update_signal(p,None,'bad',[],str(exc)); bad+=1
                if len(errors)<=10: self.container.event_logger.warning('poll_point_failed',f'Failed reading {p.asset_id}.{p.signal_name}: {exc}',{'address':p.address,'point_name':p.point_name},source='polling',asset_id=p.asset_id)
        self.container.latest_poll_errors=errors[-50:]; self.cycle_count+=1
        if self.container.storage:
            for asset_id, asset in self.container.asset_manager.snapshot().items(): self.container.storage.insert_snapshot(asset_id, asset)
        if self.cycle_count==1 or bad:
            self.container.event_logger.log('warning' if bad else 'info','poll_cycle_completed',f'Poll cycle completed: good={good}, bad={bad}',{'cycle_count':self.cycle_count,'good_points':good,'bad_points':bad},source='polling')
        return {'cycle_count':self.cycle_count,'good':good,'bad':bad,'errors':errors}
