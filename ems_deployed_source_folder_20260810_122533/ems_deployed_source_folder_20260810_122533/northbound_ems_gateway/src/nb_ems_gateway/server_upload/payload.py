from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
def build_upload_payload(container: Any, *, payload_mode: str='key_signals') -> dict[str,Any]:
    return {'schema_version':'nb_ems_gateway.telemetry.v1','timestamp_utc':datetime.now(timezone.utc).isoformat(),'gateway':{'id':container.config.gateway.id,'name':container.config.gateway.name,'mode':container.config.gateway.mode,'commands_enabled':container.config.api.commands_enabled},'network':{'field_interface':container.config.network.field_interface,'application_interface':container.config.network.application_interface,'server_upload_interface':container.config.server_upload.network_interface},'health':container.health_engine.snapshot(),'alarms':container.alarm_engine.snapshot(),'assets':container.asset_manager.snapshot(key_only=(payload_mode!='full_snapshot'))}
