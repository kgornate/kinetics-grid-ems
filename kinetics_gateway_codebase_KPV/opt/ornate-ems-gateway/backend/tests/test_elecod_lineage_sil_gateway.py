from __future__ import annotations

import json
import time
from pathlib import Path

from app.core.config import GatewayConfig, project_root
from app.services.gateway_service import GatewayService
from app.services.vendor_neutral_control import VendorNeutralPairControlService
from app.storage.sqlite_store import SQLiteStore


def make_service(tmp_path: Path) -> GatewayService:
    payload = json.loads((project_root() / "configs/elecod_lineage_4pair_sil.json").read_text())
    payload["storage"]["preferred_root"] = str(tmp_path / "storage")
    payload["storage"]["fallback_root"] = str(tmp_path / "fallback")
    payload["storage"]["sample_interval_seconds"] = 1.0
    config = GatewayConfig.model_validate(payload)
    return GatewayService(config, SQLiteStore(config.storage))


def test_sil_gateway_uses_vendor_neutral_control_and_normalized_pairs(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    assert isinstance(service.control_sequence, VendorNeutralPairControlService)
    normalized = service.normalized_snapshot()
    assert set(normalized["pairs"]) == {"pair_1", "pair_2", "pair_3", "pair_4"}
    assert normalized["battery_racks"]["1"]["state"] == "Normal"
    assert normalized["pcs"]["pcs_1"]["online"] is True


def test_sil_full_automatic_sequence_runs_through_gateway_service(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    result = service.control_sequence.automatic_start(
        "internal",
        "pair_1",
        "discharge",
        20.0,
        "EXECUTE_AUTOMATIC_SEQUENCE",
        ramp_step_kw=10.0,
        ramp_interval_seconds=0.01,
    )
    assert result["accepted"] is True
    deadline = time.time() + 2.0
    while time.time() < deadline:
        runtime = service.control_sequence.status("pair_1", fresh=True)["runtime"]
        if runtime["run_status"] in {"success", "failed"}:
            break
        time.sleep(0.02)
    runtime = service.control_sequence.status("pair_1", fresh=True)["runtime"]
    assert runtime["run_status"] == "success", runtime
    assert runtime["commanded_power_kw"] == 20.0
    verified = service.control_sequence.verify_power("pair_1")
    assert round(float(verified["actual_power"]["value"]), 3) == 20.0
