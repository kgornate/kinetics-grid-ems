from fastapi.testclient import TestClient

from nb_ems_gateway.api.server import create_app
from nb_ems_gateway.app.dependency_container import DependencyContainer
from nb_ems_gateway.auth.security import make_password_hash
from nb_ems_gateway.config.models import APIConfig, AppConfig, AuthConfig, AuthUserConfig, StorageConfig
from nb_ems_gateway.dictionary.register_map import RegisterMap
from nb_ems_gateway.protocol.reader import MockRegisterReader


def _client(tmp_path, commands_enabled=True):
    cfg = AppConfig(
        api=APIConfig(commands_enabled=commands_enabled),
        storage=StorageConfig(path=str(tmp_path / 'commands.db'), required_mount_path=None, fail_if_mount_missing=False),
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
    container.register_reader = MockRegisterReader(cfg.decoding.byte_order)
    return TestClient(create_app(container))


def _token(client, username, password):
    return client.post('/api/auth/login', json={'username': username, 'password': password}).json()['access_token']


def test_internal_can_list_ems_writable_registers(tmp_path):
    client = _client(tmp_path)
    token = _token(client, 'internal', 'internal')
    response = client.get('/api/commands/ems/registers', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 200
    data = response.json()
    assert data['asset_id'] == 'ems_system'
    assert data['count'] == 93
    assert any(item['signal_name'] == 'remote_mode' for item in data['items'])


def test_customer_cannot_access_ems_command_panel_api(tmp_path):
    client = _client(tmp_path)
    token = _token(client, 'customer', 'pw')
    response = client.get('/api/commands/ems/registers', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 403


def test_internal_can_write_ems_command_by_signal_name(tmp_path):
    client = _client(tmp_path)
    token = _token(client, 'internal', 'internal')
    response = client.post(
        '/api/commands/ems/write',
        headers={'Authorization': f'Bearer {token}'},
        json={'signal_name': 'remote_mode', 'value': 1, 'readback': True, 'note': 'unit test'},
    )
    assert response.status_code == 200
    data = response.json()
    assert data['ok'] is True
    assert data['asset_id'] == 'ems_system'
    assert data['signal_name'] == 'remote_mode'
    assert data['readback_value'] == 1


def test_command_write_disabled_by_config(tmp_path):
    client = _client(tmp_path, commands_enabled=False)
    token = _token(client, 'internal', 'internal')
    response = client.post(
        '/api/commands/ems/write',
        headers={'Authorization': f'Bearer {token}'},
        json={'signal_name': 'remote_mode', 'value': 1},
    )
    assert response.status_code == 403
