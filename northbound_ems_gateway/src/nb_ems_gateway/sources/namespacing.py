from __future__ import annotations
from typing import Any
from nb_ems_gateway.dictionary.register_map import RegisterPoint

_ASSET_SUFFIX = {
    'ems_system': 'ems_system',
    'pcs_1': 'pcs',
    'bms_1': 'bms',
    'utility_meter': 'grid_meter',
    'io_module': 'io_module',
    'liquid_cooling': 'liquid_cooling',
    'fire_protection': 'fire_protection',
    'dehumidifier': 'dehumidifier',
    'remote_control': 'remote_control',
}

def namespace_asset_id(source_id: str, base_asset_id: str) -> str:
    suffix = _ASSET_SUFFIX.get(base_asset_id, base_asset_id)
    return f"{source_id}_{suffix}"

def namespace_display_name(source_display_name: str, base_display_name: str) -> str:
    return f"{source_display_name} - {base_display_name}"

def namespace_point(point: RegisterPoint, source: Any) -> RegisterPoint:
    source_id = getattr(source, 'source_id') if not isinstance(source, dict) else source['source_id']
    source_display_name = getattr(source, 'display_name') if not isinstance(source, dict) else source.get('display_name', source_id)
    asset_id = namespace_asset_id(source_id, point.asset_id)
    asset_display_name = namespace_display_name(source_display_name, point.asset_display_name)
    return point.with_source(source_id, source_display_name, asset_id, asset_display_name)
