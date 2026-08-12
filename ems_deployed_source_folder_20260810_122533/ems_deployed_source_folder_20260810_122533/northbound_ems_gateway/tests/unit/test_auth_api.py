from fastapi.testclient import TestClient

from nb_ems_gateway.api.server import create_app
from nb_ems_gateway.app.dependency_container import DependencyContainer
from nb_ems_gateway.auth.security import make_password_hash
from nb_ems_gateway.config.models import AppConfig, AuthConfig, AuthUserConfig, StorageConfig
from nb_ems_gateway.dictionary.register_map import RegisterMap


def _client(tmp_path):
    cfg = AppConfig(
        storage=StorageConfig(path=str(tmp_path / 'auth.db'), required_mount_path=None, fail_if_mount_missing=False),
        auth=AuthConfig(
            enabled=True,
            jwt_secret='unit-test-secret',
            users=[
                AuthUserConfig(username='customer', display_name='Customer Admin', role='customer_admin', password_hash=make_password_hash('pw')),
                AuthUserConfig(username='internal', display_name='Internal Admin', role='internal_admin', password_hash=make_password_hash('internal')),
            ],
        ),
    )
    reg = RegisterMap.load('data/register_maps/china_ems_northbound_v1.json')
    container = DependencyContainer.create(config=cfg, register_map=reg)
    return TestClient(create_app(container))


def test_auth_protects_api_and_login_returns_token(tmp_path):
    client = _client(tmp_path)
    assert client.get('/api/health').status_code == 401

    login = client.post('/api/auth/login', json={'username': 'customer', 'password': 'pw'})
    assert login.status_code == 200
    token = login.json()['access_token']

    health = client.get('/api/health', headers={'Authorization': f'Bearer {token}'})
    assert health.status_code == 200
    me = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'}).json()
    assert me['role'] == 'customer_admin'


def test_customer_can_update_runtime_config(tmp_path):
    client = _client(tmp_path)
    token = client.post('/api/auth/login', json={'username': 'customer', 'password': 'pw'}).json()['access_token']
    response = client.post(
        '/api/config/runtime',
        headers={'Authorization': f'Bearer {token}'},
        json={'section': 'storage', 'values': {'retention_days': 14, 'snapshot_interval_sec': 60}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data['ok'] is True
    assert data['applied']['retention_days']['new'] == 14
