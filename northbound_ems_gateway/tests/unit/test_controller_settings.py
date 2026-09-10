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
