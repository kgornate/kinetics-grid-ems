from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from .poll_group import DEFAULT_GROUP, FAST_GROUP, SLOW_GROUP
from .poll_result import PollResult
from .polling_service import PollingService

LOGGER = logging.getLogger(__name__)


class PollingScheduler:
    def __init__(self, polling_service: PollingService, on_result: Callable[[PollResult], None], intervals: dict[str, float]) -> None:
        self.polling_service = polling_service
        self.on_result = on_result
        self.intervals = intervals
        self._tasks: list[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        self._running = True
        for group in self.polling_service.plans:
            interval = self.intervals.get(group, self.intervals.get(DEFAULT_GROUP, 5.0))
            self._tasks.append(asyncio.create_task(self._run_group(group, interval)))
        LOGGER.info("Polling scheduler started for groups: %s", sorted(self.polling_service.plans))

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _run_group(self, group: str, interval: float) -> None:
        while self._running:
            result = self.polling_service.poll_once(group)
            self.on_result(result)
            await asyncio.sleep(interval)


def intervals_from_config(config) -> dict[str, float]:
    return {
        FAST_GROUP: config.polling.fast_interval_sec,
        DEFAULT_GROUP: config.polling.default_interval_sec,
        SLOW_GROUP: config.polling.slow_interval_sec,
    }
