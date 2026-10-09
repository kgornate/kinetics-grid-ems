from __future__ import annotations

from pathlib import Path

from nb_ems_gateway.operator_control.store import ControllerMonitorStore


def test_operator_status_and_history_roundtrip(tmp_path: Path):
    store = ControllerMonitorStore(
        status_path=str(tmp_path / 'status.json'),
        history_db_path=str(tmp_path / 'history.db'),
    )
    status = {
        'timestamp_utc': '2026-08-29T06:42:29+00:00',
        'controller': {'state': 'NORMAL', 'decision': 'normal_keep_both_on_solar_on'},
        'bess': {
            'X': {'soc_percent': 95.2, 'online': True},
            'Y': {'soc_percent': 74.5, 'online': True},
        },
        'solis': {'state': 'ON', 'online': True, 'active_power_w': 34880},
    }
    store.write_status(status)
    loaded = store.read_status()
    assert loaded['available'] is True
    assert loaded['controller']['state'] == 'NORMAL'
    assert loaded['solis']['active_power_w'] == 34880

    store.append_event(
        event_type='solis_command',
        device='Solis',
        target='OFF',
        result='success',
        controller_state='BOTH_HIGH_SOLAR_OFF',
        decision='both_high_keep_both_on_solar_off',
        soc_x=98.1,
        soc_y=98.0,
        solis_state='OFF',
        solis_power_w=0,
        message='Solis command OFF verified',
        payload={'value_hex': '0x00DE'},
    )
    result = store.query_events(device='Solis', limit=10)
    assert result['total'] == 1
    assert result['items'][0]['event_type'] == 'solis_command'
    assert result['items'][0]['payload']['value_hex'] == '0x00DE'
