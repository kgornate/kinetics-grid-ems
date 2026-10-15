"""Frozen Kalpa-only S2 recording manifest. No Modbus/polling/control changes."""
from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .producer_common import fingerprint

SUPPORTED_MODES = frozenset({"PERIODIC", "ON_CHANGE_HEARTBEAT"})
SUBSTREAMS = (
    "ems_system", "pcs_extended", "bms_extended", "io_module", "liquid_cooling",
    "fire_protection", "dehumidifier", "remote_control", "utility_meter",
)

class S2PolicyError(ValueError):
    """Invalid or incomplete frozen S2 policy; never silently fall back."""

@dataclass(frozen=True)
class S2RecordingPolicy:
    point_id: str
    vendor: str
    scope: str
    key: str
    substream: str
    mode: str
    interval_sec: float
    revision: str


class S2PolicyManifest:
    def __init__(self, path: str | Path, *, expected_sha256: str | None = None):
        path = Path(path)
        raw = path.read_bytes()
        actual_sha256 = hashlib.sha256(raw).hexdigest()
        if expected_sha256 and actual_sha256 != expected_sha256:
            raise S2PolicyError("frozen S2 manifest checksum mismatch; refuse to run unapproved policies")
        data = json.loads(raw.decode("utf-8"))
        if data.get("policy_version") != "kalpa-s2-frozen-v1.0":
            raise S2PolicyError("unexpected S2 policy version")
        if data.get("substreams") != list(SUBSTREAMS):
            raise S2PolicyError("frozen S2 substreams differ from backend contract")
        points = data.get("points")
        if not isinstance(points, list) or len(points) != 2471:
            raise S2PolicyError("frozen Kalpa manifest must contain all 2471 canonical S2 points")
        self.version = data["policy_version"]
        self.source_sha256 = str(data.get("contract_sha256") or "")
        self.by_key: dict[tuple[str, str, str], S2RecordingPolicy] = {}
        total_instances = 0
        for i, p in enumerate(points):
            try:
                vendor, scope, key = (str(p[n]) for n in ("vendor", "scope", "key"))
                substream, mode = str(p["substream"]), str(p["mode"])
                interval = float(p["interval_sec"])
                point_id = str(p["point_id"])
                multiplier = int(p["expected_instances"])
            except (KeyError, TypeError, ValueError) as e:
                raise S2PolicyError(f"invalid policy at row {i}") from e
            if vendor not in {"lineage", "elecod"} or scope not in {"bank", "rack", "pcs", "environment"}:
                raise S2PolicyError(f"unexpected vendor or scope: {vendor}/{scope}")
            if mode not in SUPPORTED_MODES or substream not in SUBSTREAMS:
                raise S2PolicyError(f"invalid recording mode/substream for {point_id}")
            if not (0 < interval <= 86400) or not (1 <= multiplier <= 4):
                raise S2PolicyError(f"invalid interval or instance count for {point_id}")
            if not key or not point_id.startswith(scope + ".") or not self.source_sha256:
                raise S2PolicyError(f"invalid point identity or provenance for {point_id}")
            ident = (vendor, scope, key)
            if ident in self.by_key:
                raise S2PolicyError(f"duplicate policy: {ident}")
            revision = fingerprint([self.version, vendor, scope, key, substream, mode, interval])
            self.by_key[ident] = S2RecordingPolicy(point_id, vendor, scope, key, substream, mode, interval, revision)
            total_instances += multiplier
        if total_instances != 9494 or data.get("expected_runtime_signals") != 9494:
            raise S2PolicyError("frozen four-pair runtime count mismatch")

    def resolve(self, vendor: str, scope: str, key: str, substream: str, catalog_point: dict[str, Any] | None) -> S2RecordingPolicy:
        p = self.by_key.get((vendor, scope, key))
        if p is None:
            raise S2PolicyError(f"missing frozen S2 policy: {vendor}/{scope}/{key} (substream {substream})")
        if p.substream != substream:
            raise S2PolicyError(f"S2 substream drift: {vendor}/{scope}/{key} expected {p.substream}, got {substream}")
        if catalog_point is None or str(catalog_point.get("id")) != p.point_id:
            raise S2PolicyError(f"S2 catalog drift for {vendor}/{scope}/{key}")
        return p
