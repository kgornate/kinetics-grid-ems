from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from nb_ems_gateway.alarms.alarm_engine import AlarmEngine
from nb_ems_gateway.assets.asset_manager import AssetManager
from nb_ems_gateway.config.models import AppConfig
from nb_ems_gateway.dictionary.register_map import RegisterMap
from nb_ems_gateway.health.health_engine import HealthEngine
from nb_ems_gateway.polling.poll_result import PollResult
from nb_ems_gateway.storage.sqlite_store import SQLiteStore

LOGGER = logging.getLogger(__name__)


@dataclass
class DependencyContainer:
    config: AppConfig
    register_map: RegisterMap
    asset_manager: AssetManager
    health_engine: HealthEngine
    alarm_engine: AlarmEngine
    latest_poll_errors: list[str]
    storage: SQLiteStore | None = None

    @classmethod
    def create(cls, config: AppConfig, register_map: RegisterMap) -> "DependencyContainer":
        asset_manager = AssetManager()
        storage = None
        if config.storage.enabled:
            storage = SQLiteStore(config.storage.path)
            storage.insert_event(
                severity="info",
                event_type="gateway_startup",
                message="NorthBound EMS Gateway storage initialized in read-only mode.",
                payload={"gateway_id": config.gateway.id, "register_points": register_map.point_count},
            )
        return cls(
            config=config,
            register_map=register_map,
            asset_manager=asset_manager,
            health_engine=HealthEngine(asset_manager),
            alarm_engine=AlarmEngine(asset_manager),
            latest_poll_errors=[],
            storage=storage,
        )

    def apply_poll_result(self, result: PollResult) -> None:
        self.asset_manager.apply_poll_result(result)
        self.latest_poll_errors = list(result.errors)
        if self.storage:
            self._store_poll_result_assets(result)
            for error in result.errors:
                self.storage.insert_event("warning", "poll_error", error, {"poll_group": result.poll_group})

    def _store_poll_result_assets(self, result: PollResult) -> None:
        asset_ids = sorted({value.asset_id for value in result.values})
        for asset_id in asset_ids:
            asset_payload = self.asset_manager.get_asset(asset_id, include_telemetry=True)
            if asset_payload:
                try:
                    self.storage.insert_asset_snapshot(asset_id, asset_payload)
                except Exception as exc:  # storage must not break real-time polling
                    LOGGER.warning("Failed to store telemetry snapshot for %s: %s", asset_id, exc)

    def storage_status(self) -> dict[str, Any]:
        if not self.storage:
            return {"enabled": False}
        return self.storage.status()

    def close(self) -> None:
        if self.storage:
            self.storage.close()
