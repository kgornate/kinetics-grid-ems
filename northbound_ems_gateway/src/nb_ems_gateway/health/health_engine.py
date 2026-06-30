from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
class HealthEngine:
    def __init__(self, container: Any) -> None: self.container=container
    def snapshot(self)->dict[str,Any]:
        assets=self.container.asset_manager.asset_list()
        storage_health=self.container.storage.health() if self.container.storage else {'enabled':False}
        status='ok'
        if self.container.latest_poll_errors: status='degraded'
        if storage_health.get('enabled') and not storage_health.get('can_write',True): status='storage_warning'
        return {'status':status,'timestamp_utc':datetime.now(timezone.utc).isoformat(),'gateway_mode':self.container.config.gateway.mode,'asset_count':len(assets),'online_asset_count':sum(1 for a in assets if a['online']),'total_signal_count':sum(a['signal_count'] for a in assets),'bad_signal_count':sum(a['bad_signal_count'] for a in assets),'commands_enabled':self.container.config.api.commands_enabled,'poll_errors':self.container.latest_poll_errors[-10:],'storage_can_write':storage_health.get('can_write')}
