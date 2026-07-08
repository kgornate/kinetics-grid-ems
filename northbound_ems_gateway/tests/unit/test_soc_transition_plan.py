import importlib.util
import sys
import types
from pathlib import Path


class _DummyModbusTcpClient:  # only needed so the controller module can be imported in CI
    pass


client_mod = types.ModuleType('pymodbus.client')
client_mod.ModbusTcpClient = _DummyModbusTcpClient
client_mod.ModbusSerialClient = _DummyModbusTcpClient
pymodbus_mod = types.ModuleType('pymodbus')
pymodbus_mod.client = client_mod
sys.modules.setdefault('pymodbus', pymodbus_mod)
sys.modules.setdefault('pymodbus.client', client_mod)

_module_path = Path(__file__).resolve().parents[2] / 'tools' / 'soc_only_controller.py'
_spec = importlib.util.spec_from_file_location('soc_only_controller', _module_path)
mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules['soc_only_controller'] = mod
_spec.loader.exec_module(mod)


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


def test_no_solar_mode_still_orders_previously_off_bess_first():
    plan = mod.build_action_plan(
        mod.STATE_X_HIGH_ONLY,
        {'X': 'ON', 'Y': 'ON'},
        'OFF',
        False,
    )
    assert plan == [
        ('bess', 'X', 'ON'),
        ('bess', 'Y', 'ON'),
    ]
