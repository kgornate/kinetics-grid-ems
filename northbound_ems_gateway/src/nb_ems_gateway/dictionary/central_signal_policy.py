from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .register_map import RegisterMap


class CentralSignalPolicyError(RuntimeError):
    pass


class CentralSignalPolicy:
    """Frozen canonical Central Sync signal-policy manifest.

    The manifest is generated from the frozen Central Sync contract workbook.
    It is intentionally separate from the device register map: the register map
    defines acquisition/decoding while this manifest defines cloud-stream policy.
    """

    def __init__(self, path: str | Path) -> None:
        p = Path(path)
        if not p.is_absolute():
            p = Path.cwd() / p
        self.path = p
        try:
            raw = p.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise CentralSignalPolicyError(
                f"failed to load Central Sync signal policy {p}: {type(exc).__name__}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise CentralSignalPolicyError("Central Sync signal policy must be a JSON object")
        signals = payload.get("signals")
        if not isinstance(signals, list):
            raise CentralSignalPolicyError("Central Sync signal policy signals must be a list")

        self.payload = payload
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.signals: list[dict[str, Any]] = [dict(x) for x in signals if isinstance(x, dict)]
        self.by_point_id: dict[str, dict[str, Any]] = {}
        self.by_asset_signal: dict[tuple[str, str], dict[str, Any]] = {}
        self.s2_by_asset: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.s2_by_substream: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for item in self.signals:
            point_id = str(item.get("point_id") or "").strip()
            asset = str(item.get("asset") or "").strip()
            signal = str(item.get("signal") or "").strip()
            if not point_id or not asset or not signal:
                raise CentralSignalPolicyError("signal policy contains missing point_id/asset/signal")
            if point_id in self.by_point_id:
                raise CentralSignalPolicyError(f"duplicate point_id in signal policy: {point_id}")
            key = (asset, signal)
            if key in self.by_asset_signal:
                raise CentralSignalPolicyError(f"duplicate asset/signal in signal policy: {key}")
            self.by_point_id[point_id] = item
            self.by_asset_signal[key] = item
            if item.get("primary_stream") == "S2 general_asset_telemetry":
                self.s2_by_asset[asset].append(item)
                self.s2_by_substream[str(item.get("substream"))].append(item)

        self._validate_counts()

    def _validate_counts(self) -> None:
        counts = self.payload.get("counts") or {}
        expected = {
            "canonical_total": 1422,
            "s1_canonical": 63,
            "s2_canonical": 1350,
            "do_not_upload_canonical": 9,
            "runtime_total": 2844,
            "s1_runtime": 126,
            "s2_runtime": 2700,
            "do_not_upload_runtime": 18,
        }
        for key, value in expected.items():
            if int(counts.get(key, -1)) != value:
                raise CentralSignalPolicyError(
                    f"signal policy count mismatch {key}: expected {value}, got {counts.get(key)!r}"
                )
        if len(self.signals) != 1422:
            raise CentralSignalPolicyError(
                f"signal policy expected 1422 canonical rows, got {len(self.signals)}"
            )
        if sum(len(v) for v in self.s2_by_asset.values()) != 1350:
            raise CentralSignalPolicyError("signal policy expected exactly 1350 S2 canonical rows")

    @property
    def s2_signals(self) -> list[dict[str, Any]]:
        return [x for x in self.signals if x.get("primary_stream") == "S2 general_asset_telemetry"]

    @property
    def s2_substreams(self) -> list[str]:
        return sorted(self.s2_by_substream)

    def validate_register_map(self, register_map: RegisterMap) -> None:
        if register_map.point_count != 1422:
            raise CentralSignalPolicyError(
                f"active register map expected 1422 canonical points, got {register_map.point_count}"
            )
        actual = {p.id: p for p in register_map.points}
        if set(actual) != set(self.by_point_id):
            missing = sorted(set(self.by_point_id) - set(actual))[:10]
            extra = sorted(set(actual) - set(self.by_point_id))[:10]
            raise CentralSignalPolicyError(
                f"register map/contract point IDs differ: missing={missing} extra={extra}"
            )
        for point_id, spec in self.by_point_id.items():
            point = actual[point_id]
            checks = {
                "asset": point.asset_id,
                "signal": point.signal_name,
                "address": point.address,
                "registers": point.register_qty,
                "category": point.category,
            }
            for field, actual_value in checks.items():
                if spec.get(field) != actual_value:
                    raise CentralSignalPolicyError(
                        f"register map/contract mismatch {point_id} {field}: "
                        f"contract={spec.get(field)!r} map={actual_value!r}"
                    )

    def summary(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "contract_version": self.payload.get("contract_version"),
            "source_workbook_sha256": self.payload.get("source_workbook_sha256"),
            "counts": dict(self.payload.get("counts") or {}),
            "s2_policy_counts_canonical": dict(self.payload.get("s2_policy_counts_canonical") or {}),
            "s2_substream_counts_canonical": dict(self.payload.get("s2_substream_counts_canonical") or {}),
        }
