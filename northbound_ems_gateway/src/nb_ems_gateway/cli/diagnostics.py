from __future__ import annotations


def print_startup_banner(config, register_map, mock: bool) -> None:
    print("NorthBound EMS Gateway")
    print(f"  mode: {config.gateway.mode}")
    print(f"  mock: {mock}")
    print(f"  EMS: {config.existing_ems.host}:{config.existing_ems.port}, unit={config.existing_ems.unit_id}")
    print(f"  register points: {register_map.point_count}")
    print(f"  API: http://{config.api.host}:{config.api.port}")
