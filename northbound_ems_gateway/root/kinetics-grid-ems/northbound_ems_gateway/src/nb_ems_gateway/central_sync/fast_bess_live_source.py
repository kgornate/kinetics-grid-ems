from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class FastBESSLiveSourceError(RuntimeError):
    pass


class FastBESSLiveSource:
    """Read the Fast BESS snapshot published into volatile RAM by the gateway.

    This source never opens the NorthBound historian SQLite database and never
    polls Modbus. The producer consumes an atomic JSON snapshot written by the
    existing FastBESSLogger thread from the live AssetManager cache.
    """

    def __init__(self, path: str, *, max_snapshot_age_sec: float = 5.0) -> None:
        self.path = Path(path)
        self.max_snapshot_age_sec = float(max_snapshot_age_sec)

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            raise FastBESSLiveSourceError(f"live Fast BESS snapshot not found: {self.path}")
        try:
            raw = self.path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except Exception as exc:
            raise FastBESSLiveSourceError(f"invalid live Fast BESS snapshot: {type(exc).__name__}: {exc}") from exc

        if not isinstance(payload, dict):
            raise FastBESSLiveSourceError("live Fast BESS snapshot must be a JSON object")
        if payload.get("sample_source") != "asset_manager_live_cache":
            raise FastBESSLiveSourceError(
                f"unexpected sample_source: {payload.get('sample_source')!r}"
            )
        if payload.get("persisted_source") is not False:
            raise FastBESSLiveSourceError("live Fast BESS snapshot must declare persisted_source=false")

        sampled_ms = payload.get("sampled_at_epoch_ms")
        try:
            sampled_ms = int(sampled_ms)
        except Exception as exc:
            raise FastBESSLiveSourceError("sampled_at_epoch_ms missing or invalid") from exc

        age_sec = max(0.0, (time.time() * 1000.0 - sampled_ms) / 1000.0)
        payload["snapshot_age_sec"] = round(age_sec, 3)
        if self.max_snapshot_age_sec > 0 and age_sec > self.max_snapshot_age_sec:
            raise FastBESSLiveSourceError(
                f"live Fast BESS snapshot stale: age={age_sec:.3f}s max={self.max_snapshot_age_sec:.3f}s"
            )
        return payload
