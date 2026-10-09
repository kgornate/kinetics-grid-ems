from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nb_ems_gateway.config.models import GeneralAssetLivePublisherConfig
from nb_ems_gateway.dictionary.central_signal_policy import CentralSignalPolicy
from nb_ems_gateway.sources.namespacing import namespace_asset_id


def _parse_iso_ts(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


class GeneralAssetLivePublisher:
    """Publish S2 candidate telemetry from the live AssetManager cache into RAM.

    This component never opens the NorthBound historian SQLite database and never
    performs Modbus reads. It samples already-decoded AssetManager values in a
    dedicated thread so the synchronous Modbus polling loop cannot stretch the
    configured RAM-snapshot cadence.
    """

    def __init__(self, config: GeneralAssetLivePublisherConfig, container: Any) -> None:
        self.config = config
        self.container = container
        self.policy: CentralSignalPolicy | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False
        self.publish_count = 0
        self.failure_count = 0
        self.last_publish_utc: str | None = None
        self.last_error: str | None = None
        self.last_runtime_signal_count: int | None = None
        self.last_good_signal_count: int | None = None
        self.last_bad_signal_count: int | None = None
        self.execution_mode = "threaded"

    def load_policy(self) -> None:
        policy = CentralSignalPolicy(self.config.policy_manifest_path)
        if self.config.strict_contract:
            policy.validate_register_map(self.container.register_map)
        self.policy = policy

    async def start(self) -> None:
        if not self.config.enabled:
            return
        try:
            self.load_policy()
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.failure_count += 1
            # Cloud IPC must never prevent the field gateway from starting.
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._thread_loop,
            name="general-asset-live-publisher",
            daemon=True,
        )
        self._thread.start()

    async def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            await asyncio.to_thread(self._thread.join, 5.0)

    def _thread_loop(self) -> None:
        interval = max(0.2, float(self.config.interval_sec or 1.0))
        next_tick = time.monotonic()
        while not self._stop_event.is_set():
            start = time.monotonic()
            try:
                snapshot = self.build_snapshot()
                self.publish_snapshot(snapshot)
            except Exception as exc:
                self.failure_count += 1
                self.last_error = f"{type(exc).__name__}: {exc}"

            next_tick += interval
            delay = next_tick - time.monotonic()
            if delay < -interval:
                next_tick = time.monotonic() + interval
                delay = interval
            self._stop_event.wait(max(0.0, delay))
            if time.monotonic() - start > interval and not self._stop_event.is_set():
                time.sleep(0.01)

    def build_snapshot(self) -> dict[str, Any]:
        if self.policy is None:
            self.load_policy()
        assert self.policy is not None

        now = datetime.now(timezone.utc)
        now_ts = now.timestamp()
        records: list[dict[str, Any]] = []
        good_total = 0
        bad_total = 0
        runtime_signal_count = 0

        for source in self.container.sources:
            source_id = source.source_id
            for base_asset_id in sorted(self.policy.s2_by_asset):
                specs = self.policy.s2_by_asset[base_asset_id]
                runtime_asset_id = namespace_asset_id(source_id, base_asset_id)
                asset = self.container.asset_manager.telemetry.get(runtime_asset_id, {})
                live_signals = asset.get("signals") or {}
                signals: dict[str, dict[str, Any]] = {}
                good = 0
                bad = 0

                for spec in specs:
                    name = str(spec["signal"])
                    sig = live_signals.get(name)
                    if isinstance(sig, dict):
                        quality = str(sig.get("quality") or "unknown")
                        updated_utc = sig.get("updated_utc")
                        updated_ts = _parse_iso_ts(updated_utc)
                        age_ms = int(max(0.0, now_ts - updated_ts) * 1000) if updated_ts is not None else None
                        value = sig.get("value")
                    else:
                        quality = "missing"
                        updated_utc = None
                        age_ms = None
                        value = None

                    if quality == "good":
                        good += 1
                    else:
                        bad += 1

                    signals[name] = {
                        "point_id": spec["point_id"],
                        "value": value,
                        "quality": quality,
                        "updated_utc": updated_utc,
                        "age_ms": age_ms,
                    }

                count = len(specs)
                runtime_signal_count += count
                good_total += good
                bad_total += bad
                substreams = {str(x.get("substream")) for x in specs}
                if len(substreams) != 1:
                    raise RuntimeError(
                        f"contract asset {base_asset_id} maps to multiple S2 substreams: {sorted(substreams)}"
                    )
                records.append({
                    "source_id": source_id,
                    "source_display_name": getattr(source, "display_name", source_id),
                    "runtime_asset_id": runtime_asset_id,
                    "base_asset_id": base_asset_id,
                    "substream": next(iter(substreams)),
                    "asset_online": bool(asset.get("online", False)),
                    "asset_last_update_utc": asset.get("last_update_utc"),
                    "selected_signal_count": count,
                    "good_signal_count": good,
                    "bad_signal_count": bad,
                    "signals": signals,
                })

        return {
            "schema_version": 1,
            "sample_source": "asset_manager_live_cache",
            "persisted_source": False,
            "sampled_at_utc": now.isoformat(),
            "sampled_at_epoch_ms": int(now_ts * 1000),
            "policy_manifest_path": self.config.policy_manifest_path,
            "policy_manifest_sha256": self.policy.sha256,
            "policy_contract_version": self.policy.payload.get("contract_version"),
            "source_count": len(self.container.sources),
            "asset_record_count": len(records),
            "s2_canonical_signal_count": int(self.policy.payload["counts"]["s2_canonical"]),
            "s2_runtime_signal_count": runtime_signal_count,
            "s1_runtime_excluded_count": int(self.policy.payload["counts"]["s1_runtime"]),
            "do_not_upload_runtime_excluded_count": int(self.policy.payload["counts"]["do_not_upload_runtime"]),
            "good_signal_count": good_total,
            "bad_signal_count": bad_total,
            "records": records,
        }

    def publish_snapshot(self, snapshot: dict[str, Any]) -> None:
        path = Path(self.config.live_snapshot_path)
        tmp = path.with_name(path.name + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(snapshot, separators=(",", ":"), ensure_ascii=False) + "\n"
            tmp.write_text(raw, encoding="utf-8")
            os.chmod(tmp, 0o640)
            os.replace(tmp, path)
            self.publish_count += 1
            self.last_publish_utc = snapshot.get("sampled_at_utc")
            self.last_runtime_signal_count = int(snapshot.get("s2_runtime_signal_count") or 0)
            self.last_good_signal_count = int(snapshot.get("good_signal_count") or 0)
            self.last_bad_signal_count = int(snapshot.get("bad_signal_count") or 0)
            self.last_error = None
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    def status(self) -> dict[str, Any]:
        policy_summary = self.policy.summary() if self.policy else None
        return {
            "enabled": self.config.enabled,
            "running": self._running,
            "execution_mode": self.execution_mode,
            "thread_alive": bool(self._thread and self._thread.is_alive()),
            "interval_sec": self.config.interval_sec,
            "live_snapshot_path": self.config.live_snapshot_path,
            "policy_manifest_path": self.config.policy_manifest_path,
            "strict_contract": self.config.strict_contract,
            "publish_count": self.publish_count,
            "failure_count": self.failure_count,
            "last_publish_utc": self.last_publish_utc,
            "last_runtime_signal_count": self.last_runtime_signal_count,
            "last_good_signal_count": self.last_good_signal_count,
            "last_bad_signal_count": self.last_bad_signal_count,
            "last_error": self.last_error,
            "policy": policy_summary,
        }
