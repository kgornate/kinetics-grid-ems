from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .config import CentralSyncConfig
from .contracts import utc_now_iso
from .outbox import OutboxStore
from .producer_common import ProducerCounters, ProducerLoopMixin, emit_message, fingerprint
from .status import safe_write_json


def _load_json(path: str) -> dict[str, Any]:
    try:
        p = Path(path)
        if p.exists():
            value = json.loads(p.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
    except Exception:
        pass
    return {}


def _get(d: dict[str, Any], path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict): return None
        cur = cur.get(part)
    return cur


class ConfigurationAuditProducer(ProducerLoopMixin):
    """S8 file-backed configuration change audit.

    The first observation is a baseline only; no synthetic history is emitted.
    Secrets/password/token values are intentionally excluded.
    """

    def __init__(self, *, config: CentralSyncConfig, outbox: OutboxStore, central_sync_config_path: str | None = None) -> None:
        self.config = config
        self.producer_config = config.configuration_audit
        self.outbox = outbox
        if central_sync_config_path:
            self.producer_config.central_sync_config_path = central_sync_config_path
        self.counters = ProducerCounters()
        self.running = False
        self.started_utc = utc_now_iso()
        self._stop = asyncio.Event()
        self._state_path = Path(self.producer_config.state_file)
        self._state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        try:
            if self._state_path.exists():
                value = json.loads(self._state_path.read_text(encoding="utf-8"))
                return value if isinstance(value, dict) else {}
        except Exception:
            pass
        return {"initialized": False, "values": {}}

    def _save_state(self) -> None:
        safe_write_json(str(self._state_path), self._state)

    def _current_values(self) -> dict[str, Any]:
        central = _load_json(self.producer_config.central_sync_config_path)
        gateway = _load_json(self.producer_config.gateway_config_path)
        backend = central.get("backend") or {}
        fast = central.get("fast_bess") or {}
        general = central.get("general_assets") or {}
        outbox = central.get("outbox") or {}
        d1 = central.get("command_downlink") or {}
        identity = central.get("identity") or {}
        return {
            # Frozen S8 vocabulary
            "central_sync.enabled": central.get("enabled"),
            "central_sync.endpoint_url": (str(backend.get("base_url") or "").rstrip("/") + str(backend.get("ingest_path") or "/api/v1/ingest/batch")) if backend else None,
            "central_sync.tls_verify": backend.get("verify_tls"),
            "central_sync.fast_bess_sample_interval_sec": fast.get("poll_interval_sec", fast.get("sample_interval_sec")),
            "central_sync.general_policy_revision": "kalpa_vendor_catalog_mapping_v1",
            "central_sync.outbox_max_db_size_mb": outbox.get("max_db_size_mb"),
            "central_sync.command_poll_sec": d1.get("poll_interval_sec"),
            "gateway.software_version": identity.get("software_version") or self.config.identity.software_version,
            # Kalpa additive configuration paths
            "gateway.mode": gateway.get("mode"),
            "gateway.bms.vendor": _get(gateway, "bms.vendor"),
            "gateway.bms.host": _get(gateway, "bms.host"),
            "gateway.bms.word_order": _get(gateway, "bms.word_order"),
            "gateway.bms.address_offset": _get(gateway, "bms.address_offset"),
            "gateway.pcs.vendor": _get(gateway, "pcs.vendor"),
            "gateway.pcs.transport": _get(gateway, "pcs.transport"),
            "gateway.pcs.host": _get(gateway, "pcs.host"),
            "gateway.pcs.port": _get(gateway, "pcs.port"),
            "gateway.pcs.address_offset": _get(gateway, "pcs.address_offset"),
            "gateway.control.enabled": _get(gateway, "control_sequence.enabled"),
            "gateway.control.allow_full_automatic_sequence": _get(gateway, "control_sequence.allow_full_automatic_sequence"),
            "gateway.control.max_abs_power_kw": _get(gateway, "control_sequence.max_abs_power_kw"),
        }

    async def collect_once(self) -> dict[str, Any]:
        self.counters.poll_count += 1
        self.counters.last_poll_utc = utc_now_iso()
        current = self._current_values()
        previous = self._state.get("values") if isinstance(self._state.get("values"), dict) else {}
        if not self._state.get("initialized"):
            self._state = {"initialized": True, "values": current, "fingerprint": fingerprint(current)}
            self._save_state()
            self.counters.success_count += 1
            self.counters.last_success_utc = utc_now_iso()
            self._write_status()
            return {"emitted": False, "reason": "baseline_established", "setting_count": len(current)}

        records = []
        now = utc_now_iso()
        for path in sorted(set(previous) | set(current)):
            old = previous.get(path)
            new = current.get(path)
            if old == new:
                continue
            audit_id = str(uuid5(NAMESPACE_URL, f"{self.config.identity.gateway_id}:{path}:{fingerprint([old,new])}"))
            records.append({
                "audit_id": audit_id,
                "timestamp_utc": now,
                "gateway_id": self.config.identity.gateway_id,
                "site_id": self.config.identity.site_id,
                "actor": "gateway_config_watcher",
                "actor_role": None,
                "change_source": "config_file",
                "setting_path": path,
                "old_value": old,
                "new_value": new,
                "revision": None,
                "reason": "configuration value changed",
                "correlation_id": None,
            })

        self._state = {"initialized": True, "values": current, "fingerprint": fingerprint(current)}
        self._save_state()
        if not records:
            self.counters.success_count += 1
            self.counters.last_success_utc = now
            self._write_status()
            return {"emitted": False, "reason": "no_change"}

        inserted, msg = await asyncio.to_thread(
            emit_message, config=self.config, outbox=self.outbox,
            stream=self.producer_config.stream, substream=self.producer_config.substream,
            priority=self.producer_config.priority, records=records, created_at_utc=now,
        )
        self.counters.success_count += 1
        self.counters.last_success_utc = now
        if inserted:
            self.counters.message_count += 1
            self.counters.record_count += len(records)
            self.counters.last_enqueue_utc = now
            self.counters.last_message_id = msg.message_id
            self.counters.last_sequence = msg.sequence
        self.counters.last_error = None
        self._write_status()
        return {"emitted": bool(inserted), "record_count": len(records), "message_id": msg.message_id if msg else None}
