from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nb_ems_gateway.api.routes_operator_control import router
from nb_ems_gateway.operator_control.store import ControllerMonitorStore


def test_operator_control_api(tmp_path, monkeypatch):
    status_path = tmp_path / 'status.json'
    db_path = tmp_path / 'history.db'
    monkeypatch.setenv('NB_EMS_CONTROLLER_STATUS_PATH', str(status_path))
    monkeypatch.setenv('NB_EMS_CONTROLLER_HISTORY_DB', str(db_path))

    store = ControllerMonitorStore(str(status_path), str(db_path))
    store.write_status({
        'timestamp_utc': '2026-08-29T06:42:29+00:00',
        'controller': {'state': 'NORMAL', 'decision': 'normal_keep_both_on_solar_on'},
        'thresholds': {'high_soc_percent': 98.0, 'recovery_soc_percent': 75.0},
        'bess': {
            'X': {'soc_percent': 95.2, 'online': True},
            'Y': {'soc_percent': 74.5, 'online': True},
        },
        'solis': {'state': 'ON', 'online': True, 'active_power_w': 34880, 'active_power_kw': 34.88},
    })
    store.append_event(
        event_type='solis_command', device='Solis', target='ON', result='success',
        message='Solis command ON verified', controller_state='NORMAL',
    )
    store.append_event(
        event_type='bess_command', device='X', target='ON', result='success',
        message='BESS X command ON verified', controller_state='NORMAL',
    )

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    status = client.get('/api/controller/status')
    assert status.status_code == 200
    assert status.json()['solis']['state'] == 'ON'

    solis_status = client.get('/api/solis/status')
    assert solis_status.status_code == 200
    assert solis_status.json()['solis']['active_power_kw'] == 34.88

    history = client.get('/api/controller/history?limit=10')
    assert history.status_code == 200
    assert history.json()['total'] == 2

    solis_history = client.get('/api/solis/history?limit=10')
    assert solis_history.status_code == 200
    assert solis_history.json()['total'] == 1
    assert solis_history.json()['items'][0]['device'] == 'Solis'
