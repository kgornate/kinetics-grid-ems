import asyncio

from nb_ems_gateway.app.dependency_container import DependencyContainer
from nb_ems_gateway.config.models import APIConfig, AppConfig, ControlConfig, ExternalEMSUnitConfig, RegisterMapConfig, SOCProtectionConfig, StorageConfig
from nb_ems_gateway.control.control_service import ControlService
from nb_ems_gateway.control.soc_protection import SOCProtectionController
from nb_ems_gateway.dictionary.register_map import RegisterMap
from nb_ems_gateway.polling.scheduler import PollingScheduler
from nb_ems_gateway.protocol.reader import build_readers


def _container(tmp_path, *, soc1: float, soc2: float):
    cfg = AppConfig(
        gateway={'mode': 'ems_read_write'},
        api=APIConfig(commands_enabled=True),
        register_map=RegisterMapConfig(path='data/register_maps/unity261pv_modbus_north_v1.json'),
        storage=StorageConfig(path=str(tmp_path / 'soc.db'), required_mount_path=None, fail_if_mount_missing=False, snapshot_interval_sec=0),
        external_ems_units=[
            ExternalEMSUnitConfig(source_id='external_ems_1', display_name='Chinese EMS 1', host='192.168.100.151', port=502),
            ExternalEMSUnitConfig(source_id='external_ems_2', display_name='Chinese EMS 2', host='192.168.100.153', port=502),
        ],
        control=ControlConfig(enabled=True),
        soc_protection=SOCProtectionConfig(enabled=True, dry_run=True, command_cooldown_sec=0),
    )
    reg = RegisterMap.load(cfg.register_map.path)
    c = DependencyContainer.create(config=cfg, register_map=reg)
    readers = build_readers(cfg, mock=True)
    readers['external_ems_1'].values[80] = soc1
    readers['external_ems_2'].values[80] = soc2
    c.readers = readers
    c.control_service = ControlService(c, readers)
    c.soc_protection_controller = SOCProtectionController(c)
    asyncio.run(PollingScheduler(c, readers).poll_once())
    return c


def test_logic_1_one_high_soc_manual_off_dry_run(tmp_path):
    c = _container(tmp_path, soc1=96.0, soc2=50.0)
    result = asyncio.run(c.soc_protection_controller.evaluate_once(force=True))
    assert result['decision'] == 'logic_1_one_high_soc'
    assert result['highs'] == ['external_ems_1']
    assert result['actions'][0]['dry_run'] is True
    assert result['actions'][0]['action'] == 'manual_off'
    assert result['actions'][0]['source_id'] == 'external_ems_1'
    c.close()


def test_logic_4_both_low_soc_with_solar_moves_to_standby_dry_run(tmp_path):
    c = _container(tmp_path, soc1=8.0, soc2=9.0)
    c.soc_protection_controller.set_solar_status(available=True, generation_kw=5.0)
    result = asyncio.run(c.soc_protection_controller.evaluate_once(force=True))
    assert result['decision'] == 'logic_4_both_low_soc_solar_recovery_standby'
    assert result['lows'] == ['external_ems_1', 'external_ems_2']
    assert [a['action'] for a in result['actions']] == ['manual_off', 'manual_off', 'manual_standby', 'manual_standby']
    c.close()
