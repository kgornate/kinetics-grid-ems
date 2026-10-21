from app.assets.bms_driver import BmsModbusDriver
from app.core.catalog import ProtocolCatalog
from app.core.config import BmsConfig, RackEndpointConfig


def test_pair_bau_endpoints_follow_rack_ports() -> None:
    config = BmsConfig(
        host="192.168.111.22",
        racks=[
            RackEndpointConfig(rack_id=1, port=503, unit_id=2),
            RackEndpointConfig(rack_id=2, port=504, unit_id=2),
            RackEndpointConfig(rack_id=3, port=505, unit_id=2),
            RackEndpointConfig(rack_id=4, port=506, unit_id=2),
        ],
    )
    catalog = ProtocolCatalog.load("generated_protocols/bms_catalog.json")
    driver = BmsModbusDriver(config, catalog)
    assert driver.endpoints["bms_bank_1"].port == 503
    assert driver.endpoints["bms_bank_2"].port == 504
    assert driver.endpoints["bms_bank_3"].port == 505
    assert driver.endpoints["bms_bank_4"].port == 506
    assert all(driver.endpoints[f"bms_bank_{rack_id}"].unit_id == 1 for rack_id in range(1, 5))
