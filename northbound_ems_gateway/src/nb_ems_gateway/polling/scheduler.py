from __future__ import annotations
import asyncio
import logging
import time
from typing import Any

from nb_ems_gateway.decoding.float_codec import decode_float32
from nb_ems_gateway.sources.namespacing import namespace_point

LOGGER = logging.getLogger(__name__)

class PollingScheduler:
    def __init__(self, container: Any, readers: dict[str, Any] | Any) -> None:
        self.container = container
        if isinstance(readers, dict):
            self.readers = readers
        else:
            self.readers = {container.sources[0].source_id: readers}
        self._task = None
        self._running = False
        self.cycle_count = 0

    async def start(self) -> None:
        if not self.container.config.polling.enabled:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        self.container.event_logger.info(
            'polling_started',
            'Multi-source polling scheduler started',
            {'points_per_source': self.container.register_map.point_count, 'source_count': len(self.container.sources)},
            source='polling',
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _loop(self) -> None:
        while self._running:
            start = time.time()
            await self.poll_once()
            await asyncio.sleep(max(0.2, self.container.config.polling.default_interval_sec - (time.time() - start)))

    async def poll_once(self) -> dict[str, Any]:
        errors: list[str] = []
        good = 0
        bad = 0
        source_results: dict[str, dict[str, int]] = {}
        for source in self.container.sources:
            reader = self.readers.get(source.source_id)
            if not reader:
                msg = f'{source.source_id}: no reader configured'
                errors.append(msg)
                source_results[source.source_id] = {'good': 0, 'bad': self.container.register_map.point_count}
                continue
            s_good = 0
            s_bad = 0
            for base_point in self.container.register_map.points:
                point = namespace_point(base_point, source)
                try:
                    regs = reader.read_point(base_point)
                    val = decode_float32(regs, self.container.config.decoding.byte_order)
                    if self.container.config.decoding.apply_factor:
                        val *= base_point.factor
                    self.container.asset_manager.update_signal(point, val, 'good', regs)
                    good += 1
                    s_good += 1
                except Exception as exc:
                    err = f'{source.source_id}.{base_point.asset_id}.{base_point.signal_name}: {exc}'
                    errors.append(err)
                    self.container.asset_manager.update_signal(point, None, 'bad', [], str(exc))
                    bad += 1
                    s_bad += 1
                    if len(errors) <= 10:
                        self.container.event_logger.warning(
                            'poll_point_failed',
                            f'Failed reading {source.source_id}.{base_point.asset_id}.{base_point.signal_name}: {exc}',
                            {'source_id': source.source_id, 'host': source.host, 'address': base_point.address, 'point_name': base_point.point_name},
                            source='polling',
                            asset_id=point.asset_id,
                        )
            source_results[source.source_id] = {'good': s_good, 'bad': s_bad}
        self.container.latest_poll_errors = errors[-50:]
        self.cycle_count += 1
        if self.container.storage:
            for asset_id, asset in self.container.asset_manager.snapshot().items():
                self.container.storage.insert_snapshot(asset_id, asset)
        if self.cycle_count == 1 or bad:
            self.container.event_logger.log(
                'warning' if bad else 'info',
                'poll_cycle_completed',
                f'Poll cycle completed: good={good}, bad={bad}',
                {'cycle_count': self.cycle_count, 'good_points': good, 'bad_points': bad, 'sources': source_results},
                source='polling',
            )
        return {'cycle_count': self.cycle_count, 'good': good, 'bad': bad, 'errors': errors, 'sources': source_results}
