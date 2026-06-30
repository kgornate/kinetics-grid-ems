from nb_ems_gateway.dictionary.register_map import RegisterMap

def test_register_map_loads_full_protocol():
    m = RegisterMap.load('data/register_maps/china_ems_northbound_v1.json')
    assert m.point_count == 1421
    assert len(m.assets) == 9
    assert any(a['asset_id'] == 'bms_1' for a in m.assets)
