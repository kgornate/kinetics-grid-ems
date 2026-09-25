from __future__ import annotations

from pathlib import Path

import pytest

from nb_ems_gateway.operator_control.settings import (
    ControllerSettingsStore,
    ControllerSettingsValidationError,
)


def test_controller_settings_roundtrip_and_partial_update(tmp_path: Path):
    path = tmp_path / 'control_settings.json'
    store = ControllerSettingsStore(str(path))

    initial = store.ensure({
        'high_limit': 98.0,
        'recovery_limit': 75.0,
        'low_cutoff_limit': 10.0,
        'low_recovery_limit': 10.0,
    })
    assert initial['settings']['high_limit'] == 98.0
    assert initial['settings']['derate_soc_limit'] == 90.0
    assert initial['settings']['derate_power_kw'] == 20.0
    assert initial['revision'] == 1

    updated = store.update(
        {'high_limit': 97.0, 'recovery_limit': 76.0},
        updated_by='internal',
    )
    assert updated['changed'] is True
    assert updated['revision'] == 2
    assert updated['settings']['high_limit'] == 97.0
    assert updated['settings']['recovery_limit'] == 76.0
    assert updated['settings']['low_cutoff_limit'] == 10.0
    assert updated['changes']['high_limit'] == {'old': 98.0, 'new': 97.0}

    reread = store.read()
    assert reread['settings'] == updated['settings']
    assert reread['updated_by'] == 'internal'


def test_controller_settings_validation_rejects_invalid_order(tmp_path: Path):
    store = ControllerSettingsStore(str(tmp_path / 'control_settings.json'))
    store.ensure()

    with pytest.raises(ControllerSettingsValidationError):
        store.update({'recovery_limit': 99.0}, updated_by='internal')

    with pytest.raises(ControllerSettingsValidationError):
        store.update({'low_cutoff_limit': 20.0, 'low_recovery_limit': 10.0}, updated_by='internal')


def test_v113_settings_file_is_backward_compatibly_migrated_in_memory(tmp_path: Path):
    path = tmp_path / 'control_settings.json'
    path.write_text("""{
  "schema_version": 1,
  "revision": 7,
  "updated_at_utc": "2026-09-10T00:00:00+00:00",
  "updated_by": "field_admin",
  "values": {
    "high_limit": 98.0,
    "recovery_limit": 75.0,
    "low_cutoff_limit": 10.0,
    "low_recovery_limit": 10.0
  }
}
""")
    store = ControllerSettingsStore(str(path))
    data = store.read()
    assert data['revision'] == 7
    assert data['settings']['derate_soc_limit'] == 90.0
    assert data['settings']['derate_power_kw'] == 20.0


def test_derate_threshold_must_be_between_recovery_and_high(tmp_path: Path):
    store = ControllerSettingsStore(str(tmp_path / 'control_settings.json'))
    store.ensure()
    with pytest.raises(ControllerSettingsValidationError):
        store.update({'derate_soc_limit': 70.0}, updated_by='internal')
    with pytest.raises(ControllerSettingsValidationError):
        store.update({'derate_soc_limit': 99.0}, updated_by='internal')
