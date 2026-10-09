import importlib.util
import sys
import types
from pathlib import Path

import pytest


class _DummyClient:
    pass


client_mod = types.ModuleType('pymodbus.client')
client_mod.ModbusTcpClient = _DummyClient
client_mod.ModbusSerialClient = _DummyClient
pymodbus_mod = types.ModuleType('pymodbus')
pymodbus_mod.client = client_mod
sys.modules.setdefault('pymodbus', pymodbus_mod)
sys.modules.setdefault('pymodbus.client', client_mod)

module_path = Path(__file__).resolve().parents[2] / 'tools' / 'soc_only_controller.py'
spec = importlib.util.spec_from_file_location('soc_only_controller_derate_test', module_path)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules['soc_only_controller_derate_test'] = mod
spec.loader.exec_module(mod)


class FakeSolis:
    def __init__(self):
        self.holding = {
            mod.SOLIS_HOLDING_ON_OFF_REGISTER: mod.SOLIS_HOLDING_ON_VALUE,
            mod.SOLIS_POWER_CONTROL_ENABLE_REGISTER: mod.SOLIS_POWER_CONTROL_ENABLE_VALUE,
            mod.SOLIS_POWER_LIMIT_PERCENT_REGISTER: 11000,
        }
        self.writes = []

    def read_holding_u16(self, address):
        if address not in self.holding:
            return {'ok': False}
        return {'ok': True, 'value': self.holding[address]}

    def write_holding_u16_verified(self, address, value, retries=2):
        self.holding[address] = value
        self.writes.append((address, value))
        return {'ok': True, 'readback_verified': True, 'value': value, 'attempts': []}

    def read_input_u16s(self, address, count):
        pct = self.holding[mod.SOLIS_POWER_LIMIT_PERCENT_REGISTER]
        if address == 3004 and count == 2:
            watts = 20000 if pct == 2000 else 50000
            return {'ok': True, 'values': [(watts >> 16) & 0xFFFF, watts & 0xFFFF]}
        if address == mod.SOLIS_POWER_LIMIT_PERCENT_FEEDBACK_REGISTER and count == 1:
            return {'ok': True, 'values': [pct]}
        if address == mod.SOLIS_LIMITED_POWER_FEEDBACK_REGISTER and count == 2:
            watts = int(round(100000 * pct / 10000.0))
            return {'ok': True, 'values': [(watts >> 16) & 0xFFFF, watts & 0xFFFF]}
        if address == mod.SOLIS_POWER_LIMIT_SWITCH_FEEDBACK_REGISTER and count == 1:
            return {'ok': True, 'values': [0xAA]}
        if address == mod.SOLIS_LIMITING_STATUS_REGISTER and count == 1:
            return {'ok': True, 'values': [0x0202 if pct < 11000 else 0x0000]}
        return {'ok': False}


def cfg():
    return mod.SolisConfig(
        enabled=True,
        serial_port='/dev/fake',
        rated_power_kw=100.0,
        normal_power_percent=110.0,
    )


def test_derate_to_20kw_writes_only_percentage_when_already_on():
    client = FakeSolis()
    result = mod.command_solis(
        client, cfg(), mod.SOLAR_DERATED,
        derate_power_kw=20.0, live=True,
    )
    assert client.holding[mod.SOLIS_POWER_LIMIT_PERCENT_REGISTER] == 2000
    assert client.holding[mod.SOLIS_HOLDING_ON_OFF_REGISTER] == mod.SOLIS_HOLDING_ON_VALUE
    assert client.writes == [(mod.SOLIS_POWER_LIMIT_PERCENT_REGISTER, 2000)]
    assert result['desired_power_kw'] == 20.0
    assert result['writes'][0]['feedback_verified'] is True


def test_normal_mode_restores_field_baseline_110_percent():
    client = FakeSolis()
    client.holding[mod.SOLIS_POWER_LIMIT_PERCENT_REGISTER] = 2000
    result = mod.command_solis(
        client, cfg(), mod.SOLAR_NORMAL,
        derate_power_kw=20.0, live=True,
    )
    assert client.holding[mod.SOLIS_POWER_LIMIT_PERCENT_REGISTER] == 11000
    assert client.writes[0] == (mod.SOLIS_POWER_LIMIT_PERCENT_REGISTER, 11000)
    assert result['desired_power_percent'] == 110.0


def test_derate_refuses_write_if_active_power_control_not_enabled():
    client = FakeSolis()
    client.holding[mod.SOLIS_POWER_CONTROL_ENABLE_REGISTER] = 0x55
    with pytest.raises(RuntimeError, match='active-power control is not enabled'):
        mod.command_solis(
            client, cfg(), mod.SOLAR_DERATED,
            derate_power_kw=20.0, live=True,
        )
    assert client.writes == []


def test_solar_off_keeps_existing_3006_control_path():
    client = FakeSolis()
    result = mod.command_solis(
        client, cfg(), mod.SOLAR_OFF,
        derate_power_kw=20.0, live=True,
    )
    assert client.holding[mod.SOLIS_HOLDING_ON_OFF_REGISTER] == mod.SOLIS_HOLDING_OFF_VALUE
    assert client.writes == [(mod.SOLIS_HOLDING_ON_OFF_REGISTER, mod.SOLIS_HOLDING_OFF_VALUE)]
    assert result['target'] == mod.SOLAR_OFF
