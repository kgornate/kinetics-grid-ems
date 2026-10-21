from __future__ import annotations

from app.services.bms_pcs_control import BmsPcsControlService


def test_control_routes_have_matching_service_methods() -> None:
    required = {
        "all_pair_status",
        "all_pair_status_compact",
        "automatic_start",
        "next_step",
        "precheck",
        "start_precharge",
        "start_pcs",
        "set_power",
        "safe_stop",
        "safe_stop_all",
        "abort",
    }
    missing = sorted(name for name in required if not callable(getattr(BmsPcsControlService, name, None)))
    assert missing == []
