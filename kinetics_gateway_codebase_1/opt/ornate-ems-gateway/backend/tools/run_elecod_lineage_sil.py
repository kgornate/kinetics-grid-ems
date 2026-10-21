#!/usr/bin/env python3
"""Software-in-loop validation for the complete four-pair Lineage + Elecod path.

No network access or hardware writes are performed.  The test uses the same
GatewayService, normalized adapters, PairController, historian and mock drivers
that the production process selects through configuration.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import GatewayConfig, project_root
from app.services.gateway_service import GatewayService
from app.services.platform_readiness import RELEASE_VERSION, platform_readiness
from app.storage.sqlite_store import SQLiteStore


def wait_run(service: GatewayService, pair_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        runtime = service.control_sequence.status(pair_id, fresh=True)["runtime"]
        if runtime.get("run_status") in {"success", "failed", "aborted"}:
            return runtime
        time.sleep(0.02)
    raise TimeoutError(f"Timed out waiting for {pair_id} automatic sequence")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--power-kw", type=float, default=20.0)
    args = parser.parse_args()

    payload = json.loads((project_root() / "configs/elecod_lineage_4pair_sil.json").read_text())
    # Keep the standalone self-test fast and deterministic.
    payload["control_sequence"]["runtime_monitor_enabled"] = False
    with tempfile.TemporaryDirectory(prefix="ornate_ems_sil_") as tmp:
        payload["storage"]["preferred_root"] = str(Path(tmp) / "storage")
        payload["storage"]["fallback_root"] = str(Path(tmp) / "fallback")
        cfg = GatewayConfig.model_validate(payload)
        service = GatewayService(cfg, SQLiteStore(cfg.storage))

        results: list[dict] = []
        for pair in cfg.control_sequence.pairs:
            if not pair.enabled:
                continue
            for direction in ("discharge", "charge"):
                accepted = service.control_sequence.automatic_start(
                    "sil",
                    pair.pair_id,
                    direction,
                    args.power_kw,
                    cfg.control_sequence.automatic_confirmation_phrase,
                    ramp_step_kw=10.0,
                    ramp_interval_seconds=0.01,
                )
                runtime = wait_run(service, pair.pair_id)
                if runtime.get("run_status") != "success":
                    raise RuntimeError(f"{pair.pair_id} {direction} failed: {runtime}")
                verified = service.control_sequence.verify_power(pair.pair_id)
                expected = -abs(args.power_kw) if direction == "charge" else abs(args.power_kw)
                actual = float(verified["actual_power"]["value"])
                if abs(actual - expected) > cfg.control_sequence.power_tracking_tolerance_kw:
                    raise RuntimeError(
                        f"{pair.pair_id} {direction} actual={actual} expected={expected}"
                    )
                stopped = service.control_sequence.safe_stop(
                    "sil",
                    pair.pair_id,
                    cfg.control_sequence.confirmation_phrase,
                    open_bms=False,
                )
                if not stopped.get("ok"):
                    raise RuntimeError(f"{pair.pair_id} safe-stop failed: {stopped}")
                results.append(
                    {
                        "pair_id": pair.pair_id,
                        "direction": direction,
                        "target_kw": args.power_kw,
                        "actual_kw": actual,
                        "safe_stop": True,
                    }
                )

        output = {
            "ok": True,
            "release": RELEASE_VERSION,
            "mode": "software_in_loop",
            "hardware_access": False,
            "field_validation_complete": platform_readiness(cfg)["field_validation"]["complete"],
            "cycles": results,
            "cycle_count": len(results),
        }
        print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
