from fastapi.testclient import TestClient

from nb_ems_gateway.api.server import create_app
from nb_ems_gateway.app.dependency_container import DependencyContainer
from nb_ems_gateway.auth.security import make_password_hash
from nb_ems_gateway.config.models import APIConfig, AppConfig, AuthConfig, AuthUserConfig, ControlConfig, ExternalEMSUnitConfig, RegisterMapConfig, StorageConfig, VoltageStabilizationConfig
from nb_ems_gateway.control.control_service import ControlService
from nb_ems_gateway.dictionary.register_map import RegisterMap
from nb_ems_gateway.polling.scheduler import PollingScheduler
from nb_ems_gateway.protocol.reader import build_readers


def _container(tmp_path):
    cfg = AppConfig(
        gateway={'mode': 'ems_read_write'},
        api=APIConfig(commands_enabled=True),
        register_map=RegisterMapConfig(path='data/register_maps/unity261pv_modbus_north_v1.json'),
        storage=StorageConfig(path=str(tmp_path / 'multi.db'), required_mount_path=None, fail_if_mount_missing=False, snapshot_interval_sec=0),
        external_ems_units=[
            ExternalEMSUnitConfig(source_id='external_ems_1', display_name='Chinese EMS 1', host='192.168.100.151', port=502),
            ExternalEMSUnitConfig(source_id='external_ems_2', display_name='Chinese EMS 2', host='192.168.100.153', port=502),
        ],
        auth=AuthConfig(
            enabled=True,
            jwt_secret='test',
            users=[
                AuthUserConfig(username='customer', role='customer_admin', password_hash=make_password_hash('pw')),
                AuthUserConfig(username='internal', role='internal_admin', password_hash=make_password_hash('internal')),
            ],
        ),
        control=ControlConfig(voltage_stabilization=VoltageStabilizationConfig(stable_window_sec=1, timeout_sec=3, sample_interval_sec=0.2)),
    )
    reg = RegisterMap.load(cfg.register_map.path)
    c = DependencyContainer.create(config=cfg, register_map=reg)
    readers = build_readers(cfg, mock=True)
    c.readers = readers
    c.control_service = ControlService(c, readers)
    return c


def test_unity261pv_register_map_phase1():
    m = RegisterMap.load('data/register_maps/unity261pv_modbus_north_v1.json')
    assert m.point_count == 1422
    assert len(m.writable_points) == 92
    assert m.port == 502
    assert m.require_point(signal_name='manual_charge_value_setting').address == 42
    assert m.require_point(signal_name='manual_discharge_value_setting').address == 44
    assert m.require_point(signal_name='on_off_grid_switching').address == 164
    assert m.require_point(signal_name='pcs_on_off_grid_status').address == 180
    assert m.require_point(signal_name='phase_a_voltage').address == 346


async def _poll_once(c):
    await PollingScheduler(c, c.readers).poll_once()


def test_multi_source_assets_and_sources_api(tmp_path):
    c = _container(tmp_path)
    import asyncio
    asyncio.run(_poll_once(c))
    client = TestClient(create_app(c))
    token = client.post('/api/auth/login', json={'username': 'internal', 'password': 'internal'}).json()['access_token']
    h = {'Authorization': f'Bearer {token}'}
    sources = client.get('/api/sources', headers=h).json()
    assert sources['count'] == 2
    assets = client.get('/api/assets', headers=h).json()
    assert assets['count'] == 18
    assert any(a['asset_id'] == 'external_ems_1_pcs' for a in assets['items'])
    assert any(a['asset_id'] == 'external_ems_2_bms' for a in assets['items'])
    one = client.get('/api/sources/external_ems_1/assets', headers=h).json()
    assert one['count'] == 9
    c.close()


def test_command_and_control_auth_and_routes(tmp_path):
    c = _container(tmp_path)
    client = TestClient(create_app(c))
    customer = client.post('/api/auth/login', json={'username': 'customer', 'password': 'pw'}).json()['access_token']
    internal = client.post('/api/auth/login', json={'username': 'internal', 'password': 'internal'}).json()['access_token']
    assert client.get('/api/commands/ems/registers', headers={'Authorization': f'Bearer {customer}'}).status_code == 403
    regs = client.get('/api/commands/ems/registers?source_id=external_ems_1', headers={'Authorization': f'Bearer {internal}'}).json()
    assert regs['count'] == 92
    charge = client.post('/api/control/sources/external_ems_1/charge', headers={'Authorization': f'Bearer {internal}'}, json={'power_kw': 25}).json()
    assert charge['ok'] is True
    assert charge['write']['address'] == 42
    discharge = client.post('/api/control/sources/external_ems_2/discharge', headers={'Authorization': f'Bearer {internal}'}, json={'power_kw': 30}).json()
    assert discharge['ok'] is True
    assert discharge['write']['address'] == 44
    grid = client.post('/api/control/sources/external_ems_1/grid-mode', headers={'Authorization': f'Bearer {internal}'}, json={'target_mode': 'grid_tied'}).json()
    assert grid['ok'] is True
    assert grid['command_register'] == 164
    c.close()
