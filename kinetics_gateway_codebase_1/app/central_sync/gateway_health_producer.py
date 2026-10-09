from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from .config import CentralSyncConfig
from .contracts import utc_now_iso
from .local_gateway_api import LocalGatewayApiClient
from .outbox import OutboxStore
from .producer_common import ProducerCounters, ProducerLoopMixin, emit_message, fingerprint


def _read_float(path: str) -> float | None:
    try:
        return float(Path(path).read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _uptime() -> float | None:
    return _read_float("/proc/uptime")


def _loads() -> tuple[float | None, float | None, float | None]:
    try:
        items = Path("/proc/loadavg").read_text(encoding="utf-8").split()
        return float(items[0]), float(items[1]), float(items[2])
    except Exception:
        return None, None, None


def _memory_used_percent() -> float | None:
    try:
        values: dict[str, float] = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            k, rest = line.split(":", 1)
            values[k] = float(rest.strip().split()[0])
        total = values.get("MemTotal")
        available = values.get("MemAvailable")
        if not total or available is None:
            return None
        return round((1.0 - available / total) * 100.0, 3)
    except Exception:
        return None


_prev_cpu: tuple[float, float] | None = None

def _cpu_percent() -> float | None:
    global _prev_cpu
    try:
        parts = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
        vals = [float(x) for x in parts]
        total = sum(vals)
        idle = vals[3] + (vals[4] if len(vals) > 4 else 0.0)
        current = (total, idle)
        if _prev_cpu is None:
            _prev_cpu = current
            return None
        dt = total - _prev_cpu[0]
        di = idle - _prev_cpu[1]
        _prev_cpu = current
        if dt <= 0:
            return None
        return round(max(0.0, min(100.0, (1.0 - di / dt) * 100.0)), 3)
    except Exception:
        return None


def _interfaces() -> list[dict[str, Any]]:
    try:
        result = subprocess.run(["ip", "-j", "addr"], capture_output=True, text=True, timeout=2, check=False)
        rows = json.loads(result.stdout or "[]")
        out = []
        for row in rows:
            addrs = [x.get("local") for x in row.get("addr_info", []) if x.get("family") == "inet"]
            out.append({"name": row.get("ifname"), "up": str(row.get("operstate", "")).upper() == "UP", "ip": addrs[0] if addrs else None})
        return out
    except Exception:
        return []


def _service_active(name: str) -> bool | None:
    try:
        r = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=2, check=False)
        return r.returncode == 0 and r.stdout.strip() == "active"
    except Exception:
        return None


def _status_file(path: str) -> dict[str, Any]:
    try:
        p = Path(path)
        if p.exists():
            value = json.loads(p.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
    except Exception:
        pass
    return {}


class GatewayHealthProducer(ProducerLoopMixin):
    def __init__(self, *, config: CentralSyncConfig, outbox: OutboxStore, local_api: Any | None = None, central_status_provider: Callable[[], dict[str, Any]] | None = None) -> None:
        self.config = config
        self.producer_config = config.gateway_health
        self.outbox = outbox
        self.local_api = local_api or LocalGatewayApiClient(config.local_gateway_api)
        self._owns_api = local_api is None
        self.central_status_provider = central_status_provider
        self.counters = ProducerCounters()
        self.running = False
        self.started_utc = utc_now_iso()
        self._stop = asyncio.Event()
        self._last_fp: str | None = None
        self._last_emit_mono = 0.0

    async def close(self) -> None:
        if self._owns_api:
            await self.local_api.close()

    async def collect_once(self, *, force_heartbeat: bool = False, reason: str | None = None) -> dict[str, Any]:
        self.counters.poll_count += 1
        self.counters.last_poll_utc = utc_now_iso()
        health = await self.local_api.health()
        try:
            telemetry = await self.local_api.telemetry_snapshot()
        except Exception:
            telemetry = {}
        record = self._build_record(health, telemetry)
        # transition fingerprint ignores changing timestamps/CPU noise and focuses on core availability.
        transition_fp = fingerprint({
            "status": record.get("status"),
            "online_asset_count": record.get("online_asset_count"),
            "asset_count": record.get("asset_count"),
            "control_enabled": record.get("control_enabled"),
            "storage_can_write": record.get("storage_can_write"),
            "sources": [(x.get("source_id"), x.get("online"), x.get("bad_signal_count")) for x in record.get("sources", [])],
        })
        changed = self._last_fp is not None and transition_fp != self._last_fp
        due = force_heartbeat or self._last_fp is None or changed or (time.monotonic() - self._last_emit_mono >= self.producer_config.heartbeat_interval_sec)
        if not due:
            return {"emitted": False, "reason": "not_due"}
        priority = self.producer_config.transition_priority if changed else self.producer_config.priority
        inserted, msg = await asyncio.to_thread(
            emit_message,
            config=self.config,
            outbox=self.outbox,
            stream=self.producer_config.stream,
            substream=self.producer_config.substream,
            priority=priority,
            records=[record],
            created_at_utc=record["timestamp_utc"],
        )
        self._last_fp = transition_fp
        self._last_emit_mono = time.monotonic()
        self.counters.success_count += 1
        self.counters.last_success_utc = utc_now_iso()
        self.counters.last_error = None
        if inserted:
            self.counters.message_count += 1
            self.counters.record_count += 1
            self.counters.last_enqueue_utc = utc_now_iso()
            self.counters.last_message_id = msg.message_id
            self.counters.last_sequence = msg.sequence
        self._write_status()
        return {"emitted": bool(inserted), "message_id": msg.message_id if msg else None, "transition": changed, "reason": reason}

    def _build_record(self, health: dict[str, Any], telemetry: dict[str, Any]) -> dict[str, Any]:
        timestamp = str(health.get("timestamp") or telemetry.get("timestamp") or utc_now_iso())
        assets = list(self._assets(telemetry))
        signal_count = sum(len(a.get("telemetry") or {}) for a in assets)
        bad_count = sum(sum(1 for p in (a.get("telemetry") or {}).values() if isinstance(p, dict) and str(p.get("quality")) != "good") for a in assets)
        online = sum(1 for a in assets if a.get("online"))
        storage_raw = health.get("storage") or {}
        free = storage_raw.get("free_bytes")
        total = storage_raw.get("filesystem_total_bytes")
        used_pct = None
        if free is not None and total:
            used_pct = round((1.0 - float(free) / float(total)) * 100.0, 3)
        storage_can_write = bool(storage_raw.get("root")) and (free is None or int(free) > 0)

        sources = []
        normalized = telemetry.get("normalized") if isinstance(telemetry.get("normalized"), dict) else {}
        vendors = normalized.get("vendors") if isinstance(normalized, dict) else {}
        for kind, vendor in (("bms", (vendors or {}).get("bms")), ("pcs", (vendors or {}).get("pcs"))):
            selected = [a for a in assets if (str(a.get("asset_id") or "").startswith("pcs_") if kind == "pcs" else not str(a.get("asset_id") or "").startswith("pcs_"))]
            sources.append({
                "source_id": f"{str(vendor or kind).lower()}_{kind}_source",
                "display_name": f"{vendor or kind.upper()} {kind.upper()}",
                "host": None,
                "port": None,
                "unit_id": None,
                "interface": (health.get("network") or {}).get(f"{kind}_interface") or (health.get("network") or {}).get("field_interface"),
                "asset_count": len(selected),
                "online": bool(selected) and all(bool(a.get("online")) for a in selected),
                "online_asset_count": sum(1 for a in selected if a.get("online")),
                "signal_count": sum(len(a.get("telemetry") or {}) for a in selected),
                "bad_signal_count": sum(sum(1 for p in (a.get("telemetry") or {}).values() if isinstance(p, dict) and str(p.get("quality")) != "good") for a in selected),
                "last_update_utc": max((str(a.get("timestamp")) for a in selected if a.get("timestamp")), default=None),
            })

        outbox = self.outbox.stats()
        central = self.central_status_provider() if self.central_status_provider else _status_file(self.config.status_file)
        load1, load5, load15 = _loads()
        control = health.get("control_sequence") or {}
        cs_success = (central.get("counters") or {}).get("accepted_count") if isinstance(central, dict) else None
        cs_failure = (central.get("counters") or {}).get("transport_failure_count") if isinstance(central, dict) else None

        return {
            "status": health.get("status"),
            "timestamp_utc": timestamp,
            "gateway_mode": health.get("mode"),
            "source_count": len(sources),
            "asset_count": len(assets),
            "online_asset_count": online,
            "total_signal_count": signal_count,
            "bad_signal_count": bad_count,
            "commands_enabled": bool(control.get("enabled")),
            "control_enabled": bool(control.get("enabled")),
            "storage_can_write": storage_can_write,
            "sources": sources,
            "storage": {
                "enabled": True,
                "type": "sqlite",
                "path": storage_raw.get("database"),
                "required_mount_path": storage_raw.get("preferred_mount_point"),
                "mount_ok": storage_raw.get("preferred_mount_ready"),
                "can_write": storage_can_write,
                "reasons": [],
                "free_space_mb": round(float(free) / 1048576.0, 3) if free is not None else None,
                "total_space_mb": round(float(total) / 1048576.0, 3) if total is not None else None,
                "used_percent": used_pct,
                "db_size_mb": round(float(storage_raw.get("database_bytes") or 0) / 1048576.0, 3),
                "min_free_space_mb": None,
                "max_db_size_mb": None,
                "telemetry_history_enabled": True,
                "store_mode": storage_raw.get("storage_mode"),
                "snapshot_interval_sec": storage_raw.get("effective_sample_interval_seconds"),
                "retention_days": storage_raw.get("effective_retention_days"),
                "skipped_write_count": None,
                "last_skip_reason": None,
                "tables": {
                    "telemetry_snapshots": (storage_raw.get("records") or {}).get("telemetry"),
                    "telemetry_points": None,
                    "gateway_events": (storage_raw.get("records") or {}).get("events"),
                    "fast_bess_samples": None,
                },
            },
            # Frozen Northbound compatibility block: Kalpa does not run the legacy uploader.
            "legacy_server_upload": {
                "enabled": False, "transport": None, "endpoint_url": None, "network_interface": None,
                "source_ip": None, "payload_mode": None, "upload_interval_sec": None, "queue_size": None,
                "success_count": None, "failure_count": None, "dropped_count": None,
                "last_attempt_utc": None, "last_success_utc": None, "last_error": None,
                "last_status_code": None, "running": False,
            },
            # S1 is now produced directly from live gateway cache; these fields remain for schema compatibility.
            "fast_bess_logger": {
                "enabled": bool(self.config.fast_bess.enabled), "running": bool(self.config.fast_bess.enabled),
                "execution_mode": "central_sync_live_cache", "thread_alive": None,
                "interval_sec": self.config.fast_bess.poll_interval_sec, "retention_days": None,
                "write_mode": "rich_values", "profile_name": "kalpa_lineage_elecod_fast_v1",
                "profile_path": None, "profile_error": None, "pcs_signal_count": None,
                "bms_signal_count": None, "total_signal_count_per_bess": None, "sample_count": None,
                "write_count": None, "skipped_count": None, "last_sample_utc": None, "last_error": None,
            },
            "gateway_id": self.config.identity.gateway_id,
            "gateway_name": self.config.identity.gateway_id,
            "software_version": self.config.identity.software_version,
            "system_uptime_sec": _uptime(),
            "cpu_percent": _cpu_percent(),
            "memory_used_percent": _memory_used_percent(),
            "load_1m": load1, "load_5m": load5, "load_15m": load15,
            "internet_reachable": None,
            "interfaces": _interfaces(),
            "services": [
                {"name": "ornate-ems-gateway.service", "active": _service_active("ornate-ems-gateway.service")},
                {"name": "ornate-central-sync.service", "active": _service_active("ornate-central-sync.service")},
            ],
            "central_sync": {
                "running": bool(central.get("running", True)) if isinstance(central, dict) else True,
                "outbox_pending": outbox.get("sendable_count"),
                "outbox_oldest_age_sec": outbox.get("oldest_sendable_age_sec"),
                "last_upload_utc": central.get("last_upload_utc") if isinstance(central, dict) else None,
                "last_ack_utc": central.get("last_ack_utc") if isinstance(central, dict) else None,
                "success_count": cs_success,
                "failure_count": cs_failure,
                "last_error": central.get("last_error") if isinstance(central, dict) else None,
            },
        }

    @staticmethod
    def _assets(snapshot: dict[str, Any]):
        seen: set[str] = set()
        items = [snapshot.get("bank")]
        if isinstance(snapshot.get("bms_banks"), dict): items += list(snapshot["bms_banks"].values())
        items += list(snapshot.get("racks") or [])
        if isinstance(snapshot.get("environment"), dict): items += list(snapshot["environment"].values())
        if isinstance(snapshot.get("pcs_devices"), dict): items += list(snapshot["pcs_devices"].values())
        for a in items:
            if not isinstance(a, dict): continue
            aid = str(a.get("asset_id") or "")
            if aid and aid in seen: continue
            if aid: seen.add(aid)
            yield a
