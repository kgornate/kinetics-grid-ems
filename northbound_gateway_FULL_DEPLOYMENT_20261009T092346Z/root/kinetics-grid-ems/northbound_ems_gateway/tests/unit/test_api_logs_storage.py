from fastapi.testclient import TestClient
from nb_ems_gateway.api.server import create_app
from nb_ems_gateway.app.dependency_container import DependencyContainer
from nb_ems_gateway.config.models import AppConfig, StorageConfig
from nb_ems_gateway.dictionary.register_map import RegisterMap


def test_api_logs_and_storage_health(tmp_path):
    cfg = AppConfig(storage=StorageConfig(path=str(tmp_path / 'api.db'), required_mount_path=None, fail_if_mount_missing=False, snapshot_interval_sec=0))
    m = RegisterMap.load('data/register_maps/china_ems_northbound_v1.json')
    c = DependencyContainer.create(config=cfg, register_map=m)
    c.event_logger.warning('manual_test', 'hello', source='test', asset_id='bms_1')
    client = TestClient(create_app(c))
    assert client.get('/api/storage/health').json()['can_write'] is True
    assert client.get('/api/logs', params={'severity':'warning'}).json()['total'] >= 1
    assert client.get('/api/logs/summary').status_code == 200
    assert 'manual_test' in client.get('/api/logs/export.csv').text
    assert client.post('/api/storage/cleanup').status_code == 200
    c.close()
