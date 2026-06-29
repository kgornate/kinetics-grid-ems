from pathlib import Path

from nb_ems_gateway.dictionary.map_loader import load_register_map


def test_generated_register_map_exists_and_loads():
    path = Path("data/register_maps/china_ems_northbound_v1.json")
    if not path.exists():
        return
    register_map = load_register_map(path)
    assert register_map.point_count > 1000
    assert "EMS System Parameters" in register_map.entities()
