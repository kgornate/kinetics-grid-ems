from pathlib import Path

from app.core.catalog import ProtocolCatalog
from app.core.config import project_root


def test_bms_catalog_is_complete():
    catalog = ProtocolCatalog.load(project_root() / "generated_protocols/bms_catalog.json")
    summary = catalog.summary()
    assert summary["point_count"] == 724
    assert summary["counts"]["bank.measure"] == 44
    assert summary["counts"]["rack.measure"] == 113
    assert summary["counts"]["environment.signal"] == 146
    assert summary["writable_point_count"] > 300


def test_pcs_catalog_has_all_rows():
    catalog = ProtocolCatalog.load(project_root() / "generated_protocols/pcs_catalog.json")
    assert len(catalog.points) == 288
    assert catalog.points[0]["address"] == 0x1100
    assert catalog.points[-1]["address"] == 0x1634
