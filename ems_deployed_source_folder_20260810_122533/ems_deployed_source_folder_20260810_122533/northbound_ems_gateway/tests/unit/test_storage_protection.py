from nb_ems_gateway.config.models import StorageConfig
from nb_ems_gateway.storage.sqlite_store import SQLiteStore


def test_storage_mount_guard_blocks_unmounted(tmp_path):
    cfg = StorageConfig(path=str(tmp_path / 'x.db'), required_mount_path=str(tmp_path / 'not_mounted'), fail_if_mount_missing=False)
    store = SQLiteStore(cfg)
    h = store.health()
    assert h['mount_ok'] is False
    assert h['can_write'] is False
    before = store.skipped_write_count
    assert store.insert_event('info', 'test', 'message') is None
    assert store.skipped_write_count == before + 1
    store.close()


def test_storage_writes_without_mount_requirement(tmp_path):
    cfg = StorageConfig(path=str(tmp_path / 'x.db'), required_mount_path=None, fail_if_mount_missing=False, snapshot_interval_sec=0)
    store = SQLiteStore(cfg)
    assert store.health()['can_write'] is True
    event_id = store.insert_event('warning', 'poll_point_failed', 'bad point', source='polling', asset_id='bms_1')
    assert event_id is not None
    assert store.query_events(asset_id='bms_1')['total'] == 1
    assert 'poll_point_failed' in store.export_events_csv(limit=10)
    store.close()
