from __future__ import annotations
from typing import Any

class AlarmEngine:
    def __init__(self, container: Any) -> None:
        self.container = container

    def snapshot(self, *, source_id: str | None=None) -> dict[str, Any]:
        alarms=[]
        for asset in self.container.asset_manager.snapshot(source_id=source_id).values():
            for sig in asset.get('signals',{}).values():
                name=(sig.get('display_name') or sig.get('name') or '').lower()
                val=sig.get('value')
                if ('fault' in name or 'alarm' in name) and isinstance(val,(int,float)) and val != 0:
                    alarms.append({
                        'source_id': asset.get('source_id'),
                        'asset_id': asset['asset_id'],
                        'signal_name': sig['name'],
                        'display_name': sig['display_name'],
                        'value': val,
                        'severity': 'warning',
                    })
        return {'active_count': len(alarms), 'items': alarms}
