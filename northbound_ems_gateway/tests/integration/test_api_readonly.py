from fastapi.testclient import TestClient

from nb_ems_gateway.api.server import create_app
from nb_ems_gateway.app.dependency_container import DependencyContainer
from nb_ems_gateway.config.models import AppConfig, ExistingEMSConfig
from nb_ems_gateway.dictionary.register_map import RegisterMap


def test_api_has_no_command_routes():
    config = AppConfig(existing_ems=ExistingEMSConfig(host="127.0.0.1"))
    register_map = RegisterMap.from_points("test", "v1", [])
    app = create_app(DependencyContainer.create(config, register_map))
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    command_routes = [route.path for route in app.routes if "command" in route.path]
    assert command_routes == []
