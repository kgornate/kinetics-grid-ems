from nb_ems_gateway.app.dependency_container import DependencyContainer
from nb_ems_gateway.config.models import AppConfig, StorageConfig
from nb_ems_gateway.dictionary.register_map import RegisterMap
from nb_ems_gateway.server_upload.payload import build_upload_payload

def test_upload_payload_read_only(tmp_path):
    cfg = AppConfig(storage=StorageConfig(path=str(tmp_path / 'payload.db'), required_mount_path=None, fail_if_mount_missing=False))
    m = RegisterMap.load('data/register_maps/china_ems_northbound_v1.json')
    c = DependencyContainer.create(config=cfg, register_map=m)
    payload = build_upload_payload(c)
    assert payload['gateway']['mode'] == 'read_only'
    assert payload['gateway']['commands_enabled'] is False
    assert payload['network']['server_upload_interface'] == 'mlan0'
    c.close()
