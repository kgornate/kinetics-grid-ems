from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .config import CentralSyncConfig
from .contracts import make_message, utc_now_iso
from .outbox import OutboxCapacityError, OutboxStore
from .status import safe_write_json

log = logging.getLogger(__name__)


@dataclass
class ConfigurationAuditCounters:
    poll_count: int = 0
    poll_success_count: int = 0
    poll_failure_count: int = 0
    baseline_count: int = 0
    detected_change_count: int = 0
    emitted_change_count: int = 0
    enqueue_failure_count: int = 0
    last_poll_utc: str | None = None
    last_success_utc: str | None = None
    last_enqueue_utc: str | None = None
    last_error: str | None = None
    last_message_id: str | None = None
    last_sequence: int | None = None
    last_setting_path: str | None = None


class ConfigurationAuditProducer:
    """S8 configuration-audit producer.

    G9 behavior follows the frozen v1.3 contract:
    - first observation creates a baseline only; it does not fabricate history;
    - only settings present in both the previous and current snapshot are diffed;
    - settings first becoming available are baselined silently;
    - each changed setting is a separate durable audit event;
    - state advances only after every changed event has been durably enqueued;
    - deterministic audit/message IDs make crash/retry re-enqueue idempotent.

    The producer only reads existing configuration/settings/manifest files. It does
    not alter SOC logic, Central Sync transport, Edge-AI inference, device polling,
    or any field asset.
    """

    def __init__(
        self,
        *,
        config: CentralSyncConfig,
        outbox: OutboxStore,
        central_sync_config_path: str = "configs/central_sync.json",
    ) -> None:
        self.config = config
        self.producer_config = config.configuration_audit
        self.outbox = outbox
        self.central_sync_config_path = str(central_sync_config_path)
        self.counters = ConfigurationAuditCounters()
        self.running = False
        self.started_utc = utc_now_iso()
        self._stop = asyncio.Event()
        self._state = self._load_state()

    async def close(self) -> None:
        return None

    async def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        if not self.producer_config.enabled:
            log.info("S8 configuration-audit producer disabled")
            return
        self.running = True
        self._stop.clear()
        log.info(
            "S8 configuration-audit producer started poll=%.1fs stream=%s/%s",
            self.producer_config.poll_interval_sec,
            self.producer_config.stream,
            self.producer_config.substream,
        )
        try:
            while not self._stop.is_set():
                await self.collect_once()
                try:
                    await asyncio.wait_for(
                        self._stop.wait(),
                        timeout=max(0.2, self.producer_config.poll_interval_sec),
                    )
                except asyncio.TimeoutError:
                    pass
        finally:
            self.running = False
            self._write_status()
            log.info("S8 configuration-audit producer stopped")

    async def collect_once(self) -> dict[str, Any]:
        now_utc = utc_now_iso()
        self.counters.poll_count += 1
        self.counters.last_poll_utc = now_utc

        try:
            current = await asyncio.to_thread(self._collect_snapshot)
            self.counters.poll_success_count += 1
            self.counters.last_success_utc = now_utc
            self.counters.last_error = None
        except Exception as exc:
            self.counters.poll_failure_count += 1
            self.counters.last_error = _exc_text(exc)
            self._write_status()
            log.warning("S8 snapshot collection failed: %s", exc)
            return {
                "baseline_created": False,
                "detected_changes": 0,
                "emitted_changes": 0,
                "error": self.counters.last_error,
                "outbox": await asyncio.to_thread(self.outbox.stats),
            }

        previous = self._state.get("snapshot")
        if not isinstance(previous, dict):
            self._state = {
                "schema_version": 1,
                "baseline_created_utc": now_utc,
                "last_updated_utc": now_utc,
                "snapshot": current,
            }
            self.counters.baseline_count += 1
            await asyncio.to_thread(self._save_state)
            self._write_status()
            log.info("S8 baseline created with %d settings; no audit history emitted", len(current))
            return {
                "baseline_created": True,
                "baseline_setting_count": len(current),
                "detected_changes": 0,
                "emitted_changes": 0,
                "outbox": await asyncio.to_thread(self.outbox.stats),
            }

        # Missing sources are ignored: a temporary read/source outage must never be
        # converted into old_value -> null audit noise. Newly appearing keys are
        # baselined silently because there is no trustworthy prior value to compare.
        changed_paths = [
            path
            for path in sorted(set(previous).intersection(current))
            if _value(previous[path]) != _value(current[path])
        ]
        newly_available = sorted(set(current) - set(previous))
        self.counters.detected_change_count += len(changed_paths)

        emitted = 0
        for path in changed_paths:
            old_entry = previous[path]
            new_entry = current[path]
            record = self._make_audit_record(
                path=path,
                old_entry=old_entry,
                new_entry=new_entry,
                detected_at_utc=now_utc,
            )
            ok = await self._enqueue_record(record)
            if not ok:
                # Do not advance the baseline after an enqueue/capacity failure.
                # Already-durable deterministic events are safe to encounter again.
                self._write_status()
                return {
                    "baseline_created": False,
                    "detected_changes": len(changed_paths),
                    "emitted_changes": emitted,
                    "newly_available_baselined": 0,
                    "error": self.counters.last_error,
                    "outbox": await asyncio.to_thread(self.outbox.stats),
                }
            emitted += 1

        # Every changed event is durable at this point. Advance the snapshot as one
        # atomic state write. Preserve previously known values for temporarily absent
        # settings while silently adding settings that have become available.
        merged = dict(previous)
        merged.update(current)
        self._state["snapshot"] = merged
        self._state["last_updated_utc"] = now_utc
        if changed_paths:
            self._state["last_change_utc"] = now_utc
            self._state["last_changed_paths"] = changed_paths
        await asyncio.to_thread(self._save_state)

        self.counters.emitted_change_count += emitted
        self._write_status()
        return {
            "baseline_created": False,
            "detected_changes": len(changed_paths),
            "emitted_changes": emitted,
            "changed_paths": changed_paths,
            "newly_available_baselined": len(newly_available),
            "newly_available_paths": newly_available,
            "outbox": await asyncio.to_thread(self.outbox.stats),
        }

    def _collect_snapshot(self) -> dict[str, dict[str, Any]]:
        snapshot: dict[str, dict[str, Any]] = {}

        # 1) Revisioned controller settings. Missing file is tolerated because the
        # producer may start before the controller has created its runtime store.
        controller = _read_json_optional(self.producer_config.controller_settings_path)
        if controller:
            values = controller.get("values") if isinstance(controller.get("values"), dict) else {}
            revision = controller.get("revision")
            updated_by = str(controller.get("updated_by") or "gateway_controller_settings")
            updated_at = _as_str(controller.get("updated_at_utc"))
            system_actor = updated_by.startswith("controller_")
            for key in (
                "derate_soc_limit",
                "derate_power_kw",
                "high_limit",
                "recovery_limit",
                "low_cutoff_limit",
                "low_recovery_limit",
            ):
                if key not in values:
                    continue
                snapshot[f"controller.{key}"] = _entry(
                    values[key],
                    revision=revision,
                    actor=updated_by,
                    actor_role=None if system_actor else "internal_admin",
                    change_source="software_update" if system_actor else "local_api",
                    source_timestamp_utc=updated_at,
                )

        # low_cutoff_enabled is runtime/deployment state, not one of the revisioned
        # settings above. Prefer the controller's live status snapshot and never
        # fabricate it from a missing status file.
        controller_status = _read_json_optional(self.producer_config.controller_status_path)
        thresholds = controller_status.get("thresholds") if isinstance(controller_status.get("thresholds"), dict) else {}
        if "low_cutoff_enabled" in thresholds:
            snapshot["controller.low_cutoff_enabled"] = _entry(
                bool(thresholds.get("low_cutoff_enabled")),
                revision=None,
                actor="gateway_runtime",
                actor_role=None,
                change_source="config_file",
                source_timestamp_utc=_as_str(controller_status.get("timestamp_utc")),
            )

        # 2) Central Sync configuration. Read the file on every pass so external
        # deployment/config-file edits are observable even before a service restart.
        central_raw = _read_json(self.central_sync_config_path)
        backend = central_raw.get("backend") if isinstance(central_raw.get("backend"), dict) else {}
        identity = central_raw.get("identity") if isinstance(central_raw.get("identity"), dict) else {}
        fast = central_raw.get("fast_bess") if isinstance(central_raw.get("fast_bess"), dict) else {}
        general = central_raw.get("general_assets") if isinstance(central_raw.get("general_assets"), dict) else {}
        outbox = central_raw.get("outbox") if isinstance(central_raw.get("outbox"), dict) else {}
        command_downlink = central_raw.get("command_downlink") if isinstance(central_raw.get("command_downlink"), dict) else {}
        config_revision = "sha256:" + _stable_hash({
            "enabled": central_raw.get("enabled"),
            "endpoint_url": _endpoint_url(backend),
            "tls_verify": backend.get("verify_tls"),
            "fast_bess_sample_interval_sec": fast.get("sample_interval_sec"),
            "general_policy_revision": _policy_identity(general.get("policy_manifest_path")),
            "outbox_max_db_size_mb": outbox.get("max_db_size_mb"),
            "software_version": identity.get("software_version"),
            "command_poll_sec": command_downlink.get("poll_interval_sec"),
        })
        central_values = {
            "central_sync.enabled": central_raw.get("enabled"),
            "central_sync.endpoint_url": _endpoint_url(backend),
            "central_sync.tls_verify": backend.get("verify_tls"),
            "central_sync.fast_bess_sample_interval_sec": fast.get("sample_interval_sec"),
            "central_sync.general_policy_revision": _policy_identity(general.get("policy_manifest_path")),
            "central_sync.outbox_max_db_size_mb": outbox.get("max_db_size_mb"),
            "gateway.software_version": identity.get("software_version"),
            "central_sync.command_poll_sec": command_downlink.get("poll_interval_sec"),
        }
        for path, value in central_values.items():
            if value is None:
                continue
            snapshot[path] = _entry(
                value,
                revision=config_revision,
                actor="gateway_config",
                actor_role=None,
                change_source="software_update" if path == "gateway.software_version" else "config_file",
            )

        # 3) Edge-AI model contract metadata from the real manifest. The S8
        # producer never infers model metadata from filenames.
        manifest_path = self.producer_config.model_manifest_path or self.config.edge_ai.model_manifest_path
        manifest = _read_json_optional(manifest_path)
        if manifest:
            features = manifest.get("features") if isinstance(manifest.get("features"), list) else []
            model_revision = "sha256:" + _stable_hash({
                "version": manifest.get("version"),
                "threshold": manifest.get("threshold"),
                "feature_count": manifest.get("feature_count", len(features) if features else None),
                "threshold_direction": manifest.get("threshold_direction"),
            })
            model_values = {
                "edge_ai.model_version": manifest.get("version"),
                "edge_ai.threshold": manifest.get("threshold"),
                "edge_ai.feature_count": manifest.get("feature_count", len(features) if features else None),
                "edge_ai.threshold_direction": manifest.get("threshold_direction"),
            }
            for path, value in model_values.items():
                if value is None:
                    continue
                snapshot[path] = _entry(
                    value,
                    revision=model_revision,
                    actor="edge_ai_model_manifest",
                    actor_role=None,
                    change_source="model_update",
                )

        # D1 command_poll_sec is intentionally absent until D1 exists, exactly as
        # required by the frozen S8 contract.
        return snapshot

    def _make_audit_record(
        self,
        *,
        path: str,
        old_entry: dict[str, Any],
        new_entry: dict[str, Any],
        detected_at_utc: str,
    ) -> dict[str, Any]:
        old_value = _value(old_entry)
        new_value = _value(new_entry)
        revision = new_entry.get("revision")
        timestamp = new_entry.get("source_timestamp_utc") or detected_at_utc
        audit_id = _stable_audit_id(
            gateway_id=self.config.identity.gateway_id,
            setting_path=path,
            old_value=old_value,
            new_value=new_value,
            revision=revision,
        )
        return {
            "audit_id": audit_id,
            "timestamp_utc": timestamp,
            "gateway_id": self.config.identity.gateway_id,
            "site_id": self.config.identity.site_id,
            "actor": new_entry.get("actor") or "gateway_config",
            "actor_role": new_entry.get("actor_role"),
            "change_source": new_entry.get("change_source") or "config_file",
            "setting_path": path,
            "old_value": old_value,
            "new_value": new_value,
            "revision": revision or ("sha256:" + _stable_hash({path: new_value})),
            "reason": None,
            "correlation_id": None,
        }

    async def _enqueue_record(self, record: dict[str, Any]) -> bool:
        sequence = await asyncio.to_thread(
            self.outbox.next_sequence,
            self.producer_config.stream,
            self.producer_config.substream,
        )
        message = make_message(
            schema_version=self.config.identity.schema_version,
            gateway_id=self.config.identity.gateway_id,
            site_id=self.config.identity.site_id,
            stream=self.producer_config.stream,
            substream=self.producer_config.substream,
            sequence=sequence,
            priority=self.producer_config.priority,
            records=[record],
            created_at_utc=str(record.get("timestamp_utc") or utc_now_iso()),
            # Stable message_id closes the crash window between durable enqueue and
            # S8 state-file update. audit_id is independently stable in the record.
            message_id=str(record["audit_id"]),
        )
        try:
            inserted = await asyncio.to_thread(self.outbox.enqueue, message)
        except OutboxCapacityError as exc:
            self.counters.enqueue_failure_count += 1
            self.counters.last_error = f"outbox capacity backpressure: {_exc_text(exc)}"
            log.error("S8 paused by outbox capacity guard: %s", exc)
            return False
        except Exception as exc:
            self.counters.enqueue_failure_count += 1
            self.counters.last_error = f"outbox enqueue failed: {_exc_text(exc)}"
            log.exception("S8 enqueue failed")
            return False

        # inserted=False means the same deterministic event is already durable;
        # that is success for advancing the S8 baseline after crash recovery.
        self.counters.last_enqueue_utc = str(record.get("timestamp_utc") or utc_now_iso())
        self.counters.last_message_id = message.message_id
        self.counters.last_sequence = sequence
        self.counters.last_setting_path = str(record.get("setting_path") or "")
        return True

    def status(self) -> dict[str, Any]:
        snapshot = self._state.get("snapshot") if isinstance(self._state.get("snapshot"), dict) else {}
        return {
            "enabled": self.producer_config.enabled,
            "running": self.running,
            "started_utc": self.started_utc,
            "stream": self.producer_config.stream,
            "substream": self.producer_config.substream,
            "poll_interval_sec": self.producer_config.poll_interval_sec,
            "central_sync_config_path": self.central_sync_config_path,
            "controller_settings_path": self.producer_config.controller_settings_path,
            "controller_status_path": self.producer_config.controller_status_path,
            "model_manifest_path": self.producer_config.model_manifest_path or self.config.edge_ai.model_manifest_path,
            "state_file": self.producer_config.state_file,
            "baseline_created_utc": self._state.get("baseline_created_utc"),
            "last_change_utc": self._state.get("last_change_utc"),
            "last_changed_paths": self._state.get("last_changed_paths") or [],
            "tracked_setting_count": len(snapshot),
            "counters": self.counters.__dict__.copy(),
            "status_generated_utc": utc_now_iso(),
        }

    def _load_state(self) -> dict[str, Any]:
        try:
            data = json.loads(Path(self.producer_config.state_file).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as exc:
            log.warning("S8 state load failed; starting empty: %s", exc)
            return {}

    def _save_state(self) -> None:
        safe_write_json(self.producer_config.state_file, self._state)

    def _write_status(self) -> None:
        try:
            safe_write_json(self.producer_config.status_file, self.status())
        except Exception as exc:
            log.warning("failed to write S8 producer status: %s", exc)


def _entry(
    value: Any,
    *,
    revision: Any,
    actor: str,
    actor_role: str | None,
    change_source: str,
    source_timestamp_utc: str | None = None,
) -> dict[str, Any]:
    return {
        "value": value,
        "revision": revision,
        "actor": actor,
        "actor_role": actor_role,
        "change_source": change_source,
        "source_timestamp_utc": source_timestamp_utc,
    }


def _value(entry: Any) -> Any:
    if isinstance(entry, dict) and "value" in entry:
        return entry.get("value")
    return entry


def _read_json(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def _read_json_optional(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        return _read_json(path)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        log.warning("S8 optional source read failed path=%s error=%s", path, exc)
        return {}


def _endpoint_url(backend: dict[str, Any]) -> str | None:
    base = backend.get("base_url")
    path = backend.get("ingest_path")
    if not base:
        return None
    if not path:
        return str(base).rstrip("/")
    return str(base).rstrip("/") + "/" + str(path).lstrip("/")


def _policy_identity(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return Path(text).name if text else None


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stable_audit_id(
    *,
    gateway_id: str,
    setting_path: str,
    old_value: Any,
    new_value: Any,
    revision: Any,
) -> str:
    identity = {
        "gateway_id": gateway_id,
        "stream": "configuration_audit",
        "setting_path": setting_path,
        "old_value": old_value,
        "new_value": new_value,
        "revision": revision,
    }
    return str(uuid5(NAMESPACE_URL, json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str)))


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _exc_text(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}".strip()
    return text[:1000]
