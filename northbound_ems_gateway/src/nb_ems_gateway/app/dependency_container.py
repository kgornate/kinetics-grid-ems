from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from nb_ems_gateway.alarms.alarm_engine import AlarmEngine
from nb_ems_gateway.assets.asset_manager import AssetManager
from nb_ems_gateway.config.models import AppConfig, ExternalEMSUnitConfig
from nb_ems_gateway.dictionary.register_map import RegisterMap
from nb_ems_gateway.health.health_engine import HealthEngine
from nb_ems_gateway.logging.event_logger import EventLogger
from nb_ems_gateway.storage.sqlite_store import SQLiteStore

@dataclass
class DependencyContainer:
    config: AppConfig
    register_map: RegisterMap
    asset_manager: AssetManager
    storage: SQLiteStore | None
    event_logger: EventLogger
    health_engine: HealthEngine
    alarm_engine: AlarmEngine
    latest_poll_errors: list[str]
    sources: list[ExternalEMSUnitConfig] = field(default_factory=list)
    readers: dict[str, Any] = field(default_factory=dict)
    control_service: Any | None = None
    server_upload_service: Any | None = None

    @classmethod
    def create(cls, *, config: AppConfig, register_map: RegisterMap) -> 'DependencyContainer':
        sources = config.active_external_sources()
        storage = SQLiteStore(config.storage) if config.storage.enabled else None
        c = cls(
            config=config,
            register_map=register_map,
            asset_manager=AssetManager(register_map, sources),
            storage=storage,
            event_logger=EventLogger(storage, config.logging.min_severity, config.logging.enabled),
            health_engine=None,  # type: ignore[arg-type]
            alarm_engine=None,  # type: ignore[arg-type]
            latest_poll_errors=[],
            sources=sources,
        )
        c.health_engine = HealthEngine(c)
        c.alarm_engine = AlarmEngine(c)
        c.event_logger.info(
            'gateway_boot',
            'NorthBound EMS Gateway booted',
            {
                'version': '0.8.0-multi-source-control',
                'register_points': register_map.point_count,
                'writable_points': len(register_map.writable_points),
                'commands_enabled': config.api.commands_enabled,
                'auth_enabled': config.auth.enabled,
                'source_count': len(sources),
                'sources': [s.model_dump() for s in sources],
            },
            source='gateway',
        )
        if storage:
            h = storage.health()
            c.event_logger.info('storage_health', 'Storage initialized', h, source='storage')
        return c

    def source_by_id(self, source_id: str) -> ExternalEMSUnitConfig | None:
        return next((s for s in self.sources if s.source_id == source_id), None)

    def storage_status(self) -> dict[str, Any]:
        return self.storage.status() if self.storage else {'enabled': False}

    def server_upload_status(self) -> dict[str, Any]:
        if not self.server_upload_service:
            return {
                'enabled': self.config.server_upload.enabled,
                'transport': self.config.server_upload.transport,
                'endpoint_url': self.config.server_upload.endpoint_url,
                'network_interface': self.config.server_upload.network_interface,
                'running': False,
            }
        return self.server_upload_service.status.to_dict()

    def close(self) -> None:
        self.event_logger.info('gateway_shutdown', 'NorthBound EMS Gateway shutdown', source='gateway')
        for reader in self.readers.values():
            try:
                reader.close()
            except Exception:
                pass
        if self.storage:
            self.storage.close()
