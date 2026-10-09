from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class GeneralAssetLiveSourceError(RuntimeError):
    pass


class GeneralAssetLiveSource:
    """Read G4/S2 telemetry snapshots from volatile RAM only."""

    def __init__(
        self,
        path: str,
        *,
        max_snapshot_age_sec: float = 5.0,
        expected_policy_sha256: str | None = None,
    ) -> None:
        self.path = Path(path)
        self.max_snapshot_age_sec = float(max_snapshot_age_sec)
        self.expected_policy_sha256 = expected_policy_sha256

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            raise GeneralAssetLiveSourceError(f"live general-asset snapshot not found: {self.path}")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise GeneralAssetLiveSourceError(
                f"invalid live general-asset snapshot: {type(exc).__name__}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise GeneralAssetLiveSourceError("live general-asset snapshot must be a JSON object")
        if payload.get("sample_source") != "asset_manager_live_cache":
            raise GeneralAssetLiveSourceError(
                f"unexpected sample_source: {payload.get('sample_source')!r}"
            )
        if payload.get("persisted_source") is not False:
            raise GeneralAssetLiveSourceError("live general-asset snapshot must declare persisted_source=false")
        if self.expected_policy_sha256:
            actual = str(payload.get("policy_manifest_sha256") or "")
            if actual != self.expected_policy_sha256:
                raise GeneralAssetLiveSourceError(
                    f"policy manifest hash mismatch: expected {self.expected_policy_sha256}, got {actual}"
                )
        try:
            sampled_ms = int(payload.get("sampled_at_epoch_ms"))
        except Exception as exc:
            raise GeneralAssetLiveSourceError("sampled_at_epoch_ms missing or invalid") from exc
        age_sec = max(0.0, (time.time() * 1000.0 - sampled_ms) / 1000.0)
        payload["snapshot_age_sec"] = round(age_sec, 3)
        if self.max_snapshot_age_sec > 0 and age_sec > self.max_snapshot_age_sec:
            raise GeneralAssetLiveSourceError(
                f"live general-asset snapshot stale: age={age_sec:.3f}s max={self.max_snapshot_age_sec:.3f}s"
            )
        return payload
