import pytest
from app.core.catalog import ProtocolCatalog
from app.core.config import project_root
from app.protocols.codec import decode_point


def point(address: int):
    catalog = ProtocolCatalog.load(project_root() / "generated_protocols/pcs_catalog.json")
    return catalog.by_address(address)[0]


def test_validated_live_measurement_decoding():
    assert decode_point(point(0x1105), [7913])["value"] == pytest.approx(791.3)
    assert decode_point(point(0x1102), [65522])["value"] == pytest.approx(-1.4)
    assert decode_point(point(0x110C), [4987])["value"] == pytest.approx(49.87)


def test_operating_state_enum_and_fault_bits():
    state = point(0x1200)
    assert state["enum"]["1"] == "停机"
    fault = point(0x1211)
    assert fault["data_type"] == "U16"
    assert any(bit["bit"] == 0 for bit in fault["bitfields"])
