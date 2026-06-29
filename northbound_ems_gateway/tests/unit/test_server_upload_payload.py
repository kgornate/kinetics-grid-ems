from nb_ems_gateway.app.dependency_container import DependencyContainer
from nb_ems_gateway.config.models import AppConfig, ExistingEMSConfig
from nb_ems_gateway.dictionary.register_map import RegisterMap
from nb_ems_gateway.server_upload.payload import build_upload_payload


def test_upload_payload_contains_read_only_gateway_metadata():
    config = AppConfig(existing_ems=ExistingEMSConfig(host="127.0.0.1"))
    register_map = RegisterMap.from_points(name="test", version="v0", points=[])
    container = DependencyContainer.create(config=config, register_map=register_map)

    payload = build_upload_payload(container, payload_mode="key_signals")

    assert payload["schema_version"] == "nb_ems_gateway.telemetry.v1"
    assert payload["gateway"]["mode"] == "read_only"
    assert payload["gateway"]["commands_enabled"] is False
    assert payload["network"]["server_upload_interface"] == "mlan0"
    assert "health" in payload
    assert "alarms" in payload
    assert "assets" in payload
    container.close()
