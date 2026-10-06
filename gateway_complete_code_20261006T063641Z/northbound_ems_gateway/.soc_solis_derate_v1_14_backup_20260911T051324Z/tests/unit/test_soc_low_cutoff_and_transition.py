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


def _decide(
    soc_x,
    soc_y,
    *,
    high_limit=200.0,
    recovery_limit=0.0,
    low_cutoff_limit=10.0,
    low_recovery_limit=10.0,
    low_cutoff_enabled=True,
    controller_state=None,
    avg_soc_delta=None,
    trend_negative_delta=0.1,
):
    return mod.decide_states(
        soc_x,
        soc_y,
        high_limit=high_limit,
        recovery_limit=recovery_limit,
        low_cutoff_limit=low_cutoff_limit,
        low_cutoff_enabled=low_cutoff_enabled,
        low_recovery_limit=low_recovery_limit,
        controller_state=controller_state or mod.STATE_NORMAL,
        avg_soc_delta=avg_soc_delta,
        trend_negative_delta=trend_negative_delta,
    )


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
    decision, bess, solar, state, solar_reason, low_reason, info = _decide(
        77.0,
        72.0,
        low_cutoff_limit=75.0,
    )
    assert decision == 'y_low_cutoff_x_on_y_off'
    assert bess == {'X': 'ON', 'Y': 'OFF'}
    assert solar == mod.SOLAR_HOLD
    assert state == mod.STATE_Y_LOW_CUTOFF
    assert low_reason == 'Y_SOC_BELOW_LOW_LIMIT'


def test_both_low_enters_cutoff_state():
    decision, bess, solar, state, solar_reason, low_reason, info = _decide(
        77.0,
        72.0,
        low_cutoff_limit=80.0,
    )
    assert decision == 'both_low_cutoff_both_off'
    assert bess == {'X': 'OFF', 'Y': 'OFF'}
    assert solar == mod.SOLAR_HOLD
    assert state == mod.STATE_BOTH_LOW_CUTOFF_LOCKOUT


def test_both_low_state_clears_after_soc_recovery_and_runs_upper_logic():
    decision, bess, solar, state, solar_reason, low_reason, info = _decide(
        77.0,
        72.0,
        high_limit=200.0,
        low_cutoff_limit=10.0,
        low_recovery_limit=10.0,
        controller_state=mod.STATE_BOTH_LOW_CUTOFF_LOCKOUT,
    )
    assert info['low_state_release'] == 'both_soc_recovered'
    assert decision == 'normal_keep_both_on_solar_on'
    assert bess == {'X': 'ON', 'Y': 'ON'}
    assert solar == 'ON'
    assert state == mod.STATE_NORMAL


def test_x_low_state_holds_until_low_recovery_hysteresis():
    decision, bess, solar, state, solar_reason, low_reason, info = _decide(
        11.0,
        50.0,
        low_cutoff_limit=10.0,
        low_recovery_limit=12.0,
        controller_state=mod.STATE_X_LOW_CUTOFF,
    )
    assert decision == 'x_low_cutoff_hold_x_off_y_on_until_recovery'
    assert bess == {'X': 'OFF', 'Y': 'ON'}
    assert state == mod.STATE_X_LOW_CUTOFF

    decision, bess, solar, state, solar_reason, low_reason, info = _decide(
        12.0,
        50.0,
        high_limit=200.0,
        low_cutoff_limit=10.0,
        low_recovery_limit=12.0,
        controller_state=mod.STATE_X_LOW_CUTOFF,
    )
    assert info['low_state_release'] == 'x_soc_recovered'
    assert decision == 'normal_keep_both_on_solar_on'
    assert bess == {'X': 'ON', 'Y': 'ON'}
    assert state == mod.STATE_NORMAL


def test_stale_low_state_does_not_block_upper_logic_when_low_cutoff_disabled():
    decision, bess, solar, state, solar_reason, low_reason, info = _decide(
        100.0,
        99.0,
        high_limit=98.0,
        recovery_limit=75.0,
        low_cutoff_enabled=False,
        low_cutoff_limit=10.0,
        controller_state=mod.STATE_X_LOW_CUTOFF,
    )
    assert info['low_state_release'] == 'low_cutoff_disabled'
    assert decision == 'both_high_keep_both_on_solar_off'
    assert bess == {'X': 'ON', 'Y': 'ON'}
    assert solar == 'OFF'
    assert state == mod.STATE_BOTH_HIGH_SOLAR_OFF
