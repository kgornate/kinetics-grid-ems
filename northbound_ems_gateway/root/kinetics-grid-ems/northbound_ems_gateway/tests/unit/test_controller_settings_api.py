from __future__ import annotations

from fastapi.testclient import TestClient

from nb_ems_gateway.api.server import create_app
from nb_ems_gateway.app.dependency_container import DependencyContainer
from nb_ems_gateway.auth.security import make_password_hash
from nb_ems_gateway.config.models import AppConfig, AuthConfig, AuthUserConfig, StorageConfig
from nb_ems_gateway.dictionary.register_map import RegisterMap


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv('NB_EMS_CONTROLLER_STATUS_PATH', str(tmp_path / 'status.json'))
    monkeypatch.setenv('NB_EMS_CONTROLLER_HISTORY_DB', str(tmp_path / 'history.db'))
    monkeypatch.setenv('NB_EMS_CONTROLLER_SETTINGS_PATH', str(tmp_path / 'control_settings.json'))

    cfg = AppConfig(
        storage=StorageConfig(
            path=str(tmp_path / 'gateway.db'),
            required_mount_path=None,
            fail_if_mount_missing=False,
        ),
        auth=AuthConfig(
            enabled=True,
            jwt_secret='unit-test-secret',
            users=[
                AuthUserConfig(
                    username='customer',
                    display_name='Customer Admin',
                    role='customer_admin',
                    password_hash=make_password_hash('pw'),
                ),
                AuthUserConfig(
                    username='internal',
                    display_name='Internal Admin',
                    role='internal_admin',
                    password_hash=make_password_hash('internal'),
                ),
            ],
        ),
    )
    reg = RegisterMap.load('data/register_maps/china_ems_northbound_v1.json')
    container = DependencyContainer.create(config=cfg, register_map=reg)
    return TestClient(create_app(container))


def _token(client: TestClient, username: str, password: str) -> str:
    response = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert response.status_code == 200
    return response.json()['access_token']


def test_customer_can_read_but_cannot_write_controller_settings(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    token = _token(client, 'customer', 'pw')
    headers = {'Authorization': f'Bearer {token}'}

    read = client.get('/api/controller/settings', headers=headers)
    assert read.status_code == 200
    assert read.json()['settings']['high_limit'] == 98.0
    assert read.json()['settings']['derate_soc_limit'] == 90.0
    assert read.json()['settings']['derate_power_kw'] == 20.0

    write = client.patch(
        '/api/admin/controller/settings',
        headers=headers,
        json={'high_limit': 97.0, 'derate_soc_limit': 90.0, 'derate_power_kw': 20.0},
    )
    assert write.status_code == 403


def test_internal_admin_can_write_controller_settings(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    token = _token(client, 'internal', 'internal')
    headers = {'Authorization': f'Bearer {token}'}

    response = client.patch(
        '/api/admin/controller/settings',
        headers=headers,
        json={
            'derate_soc_limit': 91.0,
            'derate_power_kw': 20.0,
            'high_limit': 97.0,
            'recovery_limit': 76.0,
            'low_cutoff_limit': 11.0,
            'low_recovery_limit': 15.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data['ok'] is True
    assert data['changed'] is True
    assert data['effective'] == 'next_controller_cycle'
    assert data['settings']['high_limit'] == 97.0
    assert data['settings']['derate_soc_limit'] == 91.0
    assert data['settings']['derate_power_kw'] == 20.0
    assert data['settings']['low_recovery_limit'] == 15.0

    read = client.get('/api/controller/settings', headers=headers)
    assert read.status_code == 200
    assert read.json()['revision'] == 2
    assert read.json()['settings']['recovery_limit'] == 76.0


def test_internal_admin_invalid_threshold_order_is_rejected(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    token = _token(client, 'internal', 'internal')
    headers = {'Authorization': f'Bearer {token}'}

    response = client.patch(
        '/api/admin/controller/settings',
        headers=headers,
        json={'recovery_limit': 99.0},
    )
    assert response.status_code == 400
