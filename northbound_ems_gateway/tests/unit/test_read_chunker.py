from nb_ems_gateway.dictionary.register_point import RegisterPoint
from nb_ems_gateway.protocol.read_chunker import build_read_chunks


def p(address):
    return RegisterPoint(
        point_id=f"p{address}", channel_name=None, port=515, unit_id=1,
        address=address, register_qty=2, group_no=0, entity_name="EMS System Parameters",
        point_name=f"Point {address}", point_type="Float", unit=None, description=None,
        rw_flag=0, factor=1.0, asset_id="existing_ems", normalized_name=f"existing_ems.point_{address}",
    )


def test_chunker_splits_by_max_register_count():
    chunks = build_read_chunks([p(0), p(2), p(4), p(200)], max_registers_per_read=10)
    assert len(chunks) == 2
    assert chunks[0].start_address == 0
    assert chunks[0].register_count == 6
    assert chunks[1].start_address == 200
