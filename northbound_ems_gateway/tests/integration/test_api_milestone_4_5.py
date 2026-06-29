from nb_ems_gateway.api.server import create_app
from nb_ems_gateway.app.dependency_container import DependencyContainer
from nb_ems_gateway.config.models import AppConfig, ExistingEMSConfig, StorageConfig
from nb_ems_gateway.decoding.quality import PointQuality
from nb_ems_gateway.dictionary.register_map import RegisterMap
from nb_ems_gateway.dictionary.register_point import RegisterPoint
from nb_ems_gateway.polling.poll_result import DecodedPointValue, PollResult
from fastapi.testclient import TestClient


def _point() -> RegisterPoint:
    return RegisterPoint(
        point_id="bms_1_00080",
        channel_name="test",
        port=515,
        unit_id=1,
        address=80,
        register_qty=2,
        group_no=0,
        entity_name="BMS Comm Parameters 1",
        point_name="Display SOC",
        point_type="Float",
        unit="%",
        description=None,
        rw_flag=0,
        factor=1.0,
        software_access="read_only",
        normalized_name="bms_1.soc.display_percent",
        asset_id="bms_1",
        poll_group="fast",
        display_name="BMS Display SOC",
        category="soc_soh",
        dashboard_group="battery_system",
        is_key_signal=True,
    )


def test_asset_telemetry_and_storage_routes(tmp_path):
    config = AppConfig(
        existing_ems=ExistingEMSConfig(host="127.0.0.1"),
        storage=StorageConfig(enabled=True, path=str(tmp_path / "hist.db")),
    )
    register_map = RegisterMap.from_points("test", "v1", [_point()])
    container = DependencyContainer.create(config, register_map)
    container.apply_poll_result(
        PollResult(
            poll_group="fast",
            values=(
                DecodedPointValue.now(
                    point_id="bms_1_00080",
                    asset_id="bms_1",
                    normalized_name="bms_1.soc.display_percent",
                    address=80,
                    point_name="Display SOC",
                    entity_name="BMS Comm Parameters 1",
                    value=62.5,
                    unit="%",
                    quality=PointQuality.GOOD,
                    display_name="BMS Display SOC",
                    category="soc_soh",
                    dashboard_group="battery_system",
                    is_key_signal=True,
                ),
            ),
        )
    )
    client = TestClient(create_app(container))
    asset = client.get("/api/assets/bms_1/telemetry").json()
    assert asset["telemetry"]["soc.display_percent"]["value"] == 62.5
    assert asset["key_signals"]["soc.display_percent"]["display_name"] == "BMS Display SOC"
    assert client.get("/api/storage/status").json()["telemetry_snapshot_count"] >= 1
    assert client.get("/api/storage/points", params={"asset_id": "bms_1"}).json()["points"]
    container.close()
