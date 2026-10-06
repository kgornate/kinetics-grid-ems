#!/usr/bin/env python3
"""Apply the approved PV Powertech SOC/Solis runtime settings to the persistent store.

Safe for upgrading an existing v1.13 control_settings.json: the current file is read,
then only the approved v1.14 keys are changed. Existing recovery/low-SOC values remain.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nb_ems_gateway.operator_control.settings import ControllerSettingsStore


APPROVED_PATCH = {
    "derate_soc_limit": 90.0,
    "derate_power_kw": 20.0,
    "high_limit": 98.0,
}


def main() -> int:
    store = ControllerSettingsStore()
    current = store.ensure()
    result = store.update(
        APPROVED_PATCH,
        updated_by="soc_derate_v1.14_migration",
    )
    print(json.dumps({
        "before": current,
        "approved_patch": APPROVED_PATCH,
        "after": result,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
