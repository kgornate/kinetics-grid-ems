import importlib.util
import sys
import types
from pathlib import Path


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
spec = importlib.util.spec_from_file_location('soc_only_controller', module_path)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules['soc_only_controller'] = mod
spec.loader.exec_module(mod)


def test_x_high_to_both_high_orders_solar_off_before_x_on():
    plan = mod.build_action_plan(
        mod.STATE_X_HIGH_ONLY,
        {'X': 'ON', 'Y': 'ON'},
        'OFF',
        True,
    )
    assert plan == [
        ('solar', 'Solis', 'OFF'),
        ('bess', 'X', 'ON'),
        ('bess', 'Y', 'ON'),
    ]


def test_y_high_to_both_high_orders_solar_off_before_y_on():
    plan = mod.build_action_plan(
        mod.STATE_Y_HIGH_ONLY,
        {'X': 'ON', 'Y': 'ON'},
        'OFF',
        True,
    )
    assert plan == [
        ('solar', 'Solis', 'OFF'),
        ('bess', 'Y', 'ON'),
        ('bess', 'X', 'ON'),
    ]


def test_y_low_cutoff_has_highest_priority_and_holds_solar():
    decision, bess, solar, state, solar_reason, low_reason, info = mod.decide_states(
        77.0,
        72.0,
        high_limit=200.0,
        recovery_limit=0.0,
        low_cutoff_limit=75.0,
        controller_state=mod.STATE_NORMAL,
        avg_soc_delta=None,
        trend_negative_delta=0.1,
    )
    assert decision == 'y_low_cutoff_x_on_y_off'
    assert bess == {'X': 'ON', 'Y': 'OFF'}
    assert solar == mod.SOLAR_HOLD
    assert state == mod.STATE_Y_LOW_CUTOFF
    assert low_reason == 'Y_SOC_BELOW_LOW_LIMIT'


def test_both_low_enters_persistent_lockout():
    decision, bess, solar, state, solar_reason, low_reason, info = mod.decide_states(
        77.0,
        72.0,
        high_limit=200.0,
        recovery_limit=0.0,
        low_cutoff_limit=80.0,
        controller_state=mod.STATE_NORMAL,
        avg_soc_delta=None,
        trend_negative_delta=0.1,
    )
    assert decision == 'both_low_cutoff_lockout_both_off'
    assert bess == {'X': 'OFF', 'Y': 'OFF'}
    assert solar == mod.SOLAR_HOLD
    assert state == mod.STATE_BOTH_LOW_CUTOFF_LOCKOUT


def test_both_low_lockout_persists_even_if_soc_recovers_until_clear_state():
    decision, bess, solar, state, solar_reason, low_reason, info = mod.decide_states(
        77.0,
        72.0,
        high_limit=200.0,
        recovery_limit=0.0,
        low_cutoff_limit=10.0,
        controller_state=mod.STATE_BOTH_LOW_CUTOFF_LOCKOUT,
        avg_soc_delta=None,
        trend_negative_delta=0.1,
    )
    assert decision == 'both_low_cutoff_lockout_hold_both_off'
    assert bess == {'X': 'OFF', 'Y': 'OFF'}
    assert state == mod.STATE_BOTH_LOW_CUTOFF_LOCKOUT
