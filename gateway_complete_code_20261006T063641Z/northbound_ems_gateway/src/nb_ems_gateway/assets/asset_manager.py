from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

from nb_ems_gateway.dictionary.register_map import RegisterMap, RegisterPoint
from nb_ems_gateway.sources.namespacing import namespace_asset_id, namespace_display_name

class AssetManager:
    def __init__(self, register_map: RegisterMap, sources: list[Any] | None = None) -> None:
        self.register_map = register_map
        self.sources = sources or []
        self.telemetry: dict[str, dict[str, Any]] = {}
        if self.sources:
            for source in self.sources:
                for asset in register_map.assets:
                    aid = namespace_asset_id(source.source_id, asset['asset_id'])
                    self.telemetry[aid] = self._empty_asset(
                        aid,
                        namespace_display_name(source.display_name, asset.get('display_name', asset['asset_id'])),
                        source_id=source.source_id,
                        source_display_name=source.display_name,
                        source_host=getattr(source, 'host', None),
                        source_port=getattr(source, 'port', None),
                        base_asset_id=asset['asset_id'],
                    )
        else:
            for asset in register_map.assets:
                self.telemetry[asset['asset_id']] = self._empty_asset(asset['asset_id'], asset.get('display_name', asset['asset_id']))

    def _empty_asset(self, asset_id: str, display_name: str, **meta: Any) -> dict[str, Any]:
        return {
            'asset_id': asset_id,
            'display_name': display_name,
            'online': False,
            'last_update_utc': None,
            'signal_count': 0,
            'bad_signal_count': 0,
            'signals': {},
            'key_signals': {},
            **{k: v for k, v in meta.items() if v is not None},
        }

    def update_signal(self, point: RegisterPoint, value: float | None, quality: str='good', raw_registers: list[int] | None=None, error: str | None=None) -> None:
        asset = self.telemetry.setdefault(point.asset_id, self._empty_asset(
            point.asset_id,
            point.asset_display_name,
            source_id=point.source_id or None,
            source_display_name=point.source_display_name or None,
            base_asset_id=point.base_asset_id or None,
        ))
        sig = {
            'name': point.signal_name,
            'display_name': point.point_name,
            'value': value,
            'unit': point.unit,
            'category': point.category,
            'quality': quality,
            'address': point.address,
            'raw_registers': raw_registers or [],
            'description': point.description,
            'updated_utc': datetime.now(timezone.utc).isoformat(),
            'source_id': point.source_id or asset.get('source_id'),
            'base_asset_id': point.base_asset_id or point.asset_id,
            'base_signal_name': point.base_signal_name or point.signal_name,
            'rw': point.rw,
        }
        if error:
            sig['error'] = error
        asset['signals'][point.signal_name] = sig
        if point.key_signal:
            asset['key_signals'][point.signal_name] = sig
        asset['online'] = quality == 'good' or asset.get('online', False)
        asset['last_update_utc'] = sig['updated_utc']
        asset['signal_count'] = len(asset['signals'])
        asset['bad_signal_count'] = sum(1 for s in asset['signals'].values() if s.get('quality') != 'good')

    def snapshot(self, *, asset_id: str | None=None, category: str | None=None, key_only: bool=False, source_id: str | None=None) -> dict[str, Any]:
        ids = [asset_id] if asset_id else sorted(self.telemetry)
        out: dict[str, Any] = {}
        for aid in ids:
            if aid not in self.telemetry:
                continue
            asset = self.telemetry[aid]
            if source_id and asset.get('source_id') != source_id:
                continue
            signals = asset['key_signals'] if key_only else asset['signals']
            if category:
                signals = {k: v for k, v in signals.items() if v.get('category') == category}
            item = {k: v for k, v in asset.items() if k not in ['signals', 'key_signals']}
            item['signals'] = signals
            item['key_signals'] = asset['key_signals']
            out[aid] = item
        return out

    def asset_list(self, *, source_id: str | None=None) -> list[dict[str, Any]]:
        items=[]
        for aid, a in sorted(self.telemetry.items()):
            if source_id and a.get('source_id') != source_id:
                continue
            items.append({
                'asset_id': aid,
                'display_name': a.get('display_name', aid),
                'source_id': a.get('source_id'),
                'source_display_name': a.get('source_display_name'),
                'source_host': a.get('source_host'),
                'source_port': a.get('source_port'),
                'base_asset_id': a.get('base_asset_id'),
                'online': a.get('online', False),
                'signal_count': a.get('signal_count', 0),
                'bad_signal_count': a.get('bad_signal_count', 0),
                'last_update_utc': a.get('last_update_utc'),
            })
        return items

    def source_summary(self, source_id: str) -> dict[str, Any]:
        assets = self.asset_list(source_id=source_id)
        return {
            'source_id': source_id,
            'asset_count': len(assets),
            'online': any(a.get('online') for a in assets),
            'online_asset_count': sum(1 for a in assets if a.get('online')),
            'signal_count': sum(int(a.get('signal_count') or 0) for a in assets),
            'bad_signal_count': sum(int(a.get('bad_signal_count') or 0) for a in assets),
            'last_update_utc': max([a.get('last_update_utc') or '' for a in assets], default=None) or None,
        }
