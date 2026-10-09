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
    derate_soc_limit=150.0,
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
        derate_soc_limit=derate_soc_limit,
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
    assert decision == 'normal_keep_both_on_solar_normal'
    assert bess == {'X': 'ON', 'Y': 'ON'}
    assert solar == mod.SOLAR_NORMAL
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
    assert decision == 'normal_keep_both_on_solar_normal'
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
    assert solar == mod.SOLAR_OFF
    assert state == mod.STATE_BOTH_HIGH_SOLAR_OFF


def test_both_strictly_above_90_derates_solar_to_20kw_mode():
    decision, bess, solar, state, solar_reason, low_reason, info = _decide(
        90.1, 91.0,
        high_limit=98.0,
        recovery_limit=75.0,
        derate_soc_limit=90.0,
        low_cutoff_enabled=False,
    )
    assert decision == 'both_above_90_keep_bess_on_solar_derated'
    assert bess == {'X': 'ON', 'Y': 'ON'}
    assert solar == mod.SOLAR_DERATED
    assert state == mod.STATE_BOTH_SOLAR_DERATED
    assert info['both_above_derate'] is True


def test_exactly_90_does_not_enter_derate_region():
    decision, bess, solar, state, *_ = _decide(
        90.0, 95.0,
        high_limit=98.0,
        recovery_limit=75.0,
        derate_soc_limit=90.0,
        low_cutoff_enabled=False,
    )
    assert decision == 'normal_keep_both_on_solar_normal'
    assert bess == {'X': 'ON', 'Y': 'ON'}
    assert solar == mod.SOLAR_NORMAL
    assert state == mod.STATE_NORMAL


def test_both_at_98_uses_existing_solar_off_logic():
    decision, bess, solar, state, solar_reason, *_ = _decide(
        98.0, 98.0,
        high_limit=98.0,
        recovery_limit=75.0,
        derate_soc_limit=90.0,
        low_cutoff_enabled=False,
    )
    assert decision == 'both_high_keep_both_on_solar_off'
    assert bess == {'X': 'ON', 'Y': 'ON'}
    assert solar == mod.SOLAR_OFF
    assert state == mod.STATE_BOTH_HIGH_SOLAR_OFF
    assert solar_reason == 'BOTH_BESS_HIGH'


def test_one_at_98_other_below_90_keeps_solar_normal_and_protects_high_bess():
    decision, bess, solar, state, *_ = _decide(
        99.0, 85.0,
        high_limit=98.0,
        recovery_limit=75.0,
        derate_soc_limit=90.0,
        low_cutoff_enabled=False,
    )
    assert decision == 'only_x_high_x_off_y_on_solar_normal'
    assert bess == {'X': 'OFF', 'Y': 'ON'}
    assert solar == mod.SOLAR_NORMAL
    assert state == mod.STATE_X_HIGH_ONLY


def test_one_at_98_and_other_above_90_derates_and_protects_high_bess():
    decision, bess, solar, state, *_ = _decide(
        99.0, 95.0,
        high_limit=98.0,
        recovery_limit=75.0,
        derate_soc_limit=90.0,
        low_cutoff_enabled=False,
    )
    assert decision == 'only_x_high_x_off_y_on_solar_derated'
    assert bess == {'X': 'OFF', 'Y': 'ON'}
    assert solar == mod.SOLAR_DERATED
    assert state == mod.STATE_X_HIGH_ONLY


def test_derated_to_both_high_orders_solar_off_first():
    plan = mod.build_action_plan(
        mod.STATE_BOTH_SOLAR_DERATED,
        {'X': 'ON', 'Y': 'ON'},
        mod.SOLAR_OFF,
        True,
    )
    assert plan[0] == ('solar', 'Solis', mod.SOLAR_OFF)


def test_derate_kw_to_percentage_raw_matches_field_validation():
    assert mod._kw_to_solis_percent_raw(20.0, 100.0) == 2000
    assert mod._percent_to_solis_raw(110.0) == 11000
