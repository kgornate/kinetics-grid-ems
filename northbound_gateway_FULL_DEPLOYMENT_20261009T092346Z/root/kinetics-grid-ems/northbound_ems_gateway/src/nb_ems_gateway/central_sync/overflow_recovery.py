from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import CentralBackendClient
from .config import CentralSyncConfig
from .outbox import OutboxStore
from .status import safe_write_json, utc_now_iso
from .transport_control import TransportPauseController
from .uploader import CentralSyncUploader

log = logging.getLogger(__name__)


@dataclass
class RecoveryCounters:
    scan_count: int = 0
    request_cycle_count: int = 0
    pause_transport_count: int = 0
    pause_live_count: int = 0
    pause_memory_count: int = 0
    pause_load_count: int = 0
    archive_open_count: int = 0
    archive_drained_count: int = 0
    retained_drained_count: int = 0
    failure_count: int = 0
    last_archive_path: str | None = None
    last_request_utc: str | None = None
    last_success_utc: str | None = None
    last_pause_reason: str | None = None
    last_error: str | None = None


class _LiveOutboxProbe:
    """Read-only live outbox health probe used by the recovery gate."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def snapshot(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"available": False, "reason": "live_outbox_missing"}
        uri = f"file:{self.path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=1.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("PRAGMA busy_timeout=1000")
            row = conn.execute(
                """SELECT COUNT(*) AS n,MIN(created_epoch) AS oldest
                   FROM outbox_messages
                   WHERE state IN ('pending','retry','inflight')"""
            ).fetchone()
            count = int(row["n"] or 0)
            oldest = row["oldest"]
            return {
                "available": True,
                "unacked_count": count,
                "oldest_age_sec": max(0.0, time.time() - float(oldest)) if oldest else None,
            }
        finally:
            conn.close()


class OverflowRecoveryService:
    """Opportunistically replay only overflow segments produced by this gateway.

    This is intentionally distinct from the legacy historical backlog replayer.
    It only scans ``overflow_recovery.archive_glob`` (default
    ``central_sync_overflow_*.db``), always yields to live traffic, shares the
    live uploader's transport lock/client, and never deletes archive databases.

    Therefore:
      * S1-S8 producers keep logging while transport is paused/offline.
      * old live rows may spill into bounded overflow DBs.
      * after transport recovers, live traffic wins first.
      * overflow rows are replayed through the same backend contract, one
        request at a time, only while live health is good.
      * the legacy ~1 GB historical backlog DB is not touched automatically.
    """

    def __init__(
        self,
        config: CentralSyncConfig,
        *,
        transport_lock: asyncio.Lock,
        client: CentralBackendClient | Any,
    ) -> None:
        self.config = config
        self.recovery_config = config.overflow_recovery
        self.transport_lock = transport_lock
        self.client = client
        self.live_probe = _LiveOutboxProbe(config.outbox.path)
        self.pause = TransportPauseController(config.uploader.pause_file)
        self.counters = RecoveryCounters()
        self.started_utc = utc_now_iso()
        self.running = False
        self._stop = asyncio.Event()

    async def stop(self) -> None:
        self._stop.set()

    async def close(self) -> None:
        # The shared client is owned/closed by CentralSyncUploader.
        return None

    async def run_forever(self) -> None:
        if not self.recovery_config.enabled:
            log.info("central sync overflow recovery disabled")
            self._write_status()
            return
        self.running = True
        self._stop.clear()
        log.info(
            "central sync overflow recovery started dir=%s glob=%s batch=%s bytes=%s pause=%.1fs",
            self.recovery_config.archive_dir,
            self.recovery_config.archive_glob,
            self.recovery_config.max_messages_per_request,
            self.recovery_config.max_request_bytes,
            self.recovery_config.request_pause_sec,
        )
        try:
            while not self._stop.is_set():
                self.counters.scan_count += 1
                allowed, reason, health = await asyncio.to_thread(self._resource_gate)
                if not allowed:
                    self.counters.last_pause_reason = reason
                    self._write_status(extra={"resource_gate": health})
                    await self._sleep(self.recovery_config.scan_interval_sec)
                    continue

                archive_path = await asyncio.to_thread(self._next_archive)
                if archive_path is None:
                    self.counters.last_pause_reason = "no_overflow_backlog"
                    self._write_status(extra={"resource_gate": health})
                    await self._sleep(self.recovery_config.scan_interval_sec)
                    continue

                try:
                    sent = await self._replay_one(archive_path)
                    self.counters.last_pause_reason = None
                    self.counters.last_error = None
                    self._write_status(extra={"resource_gate": health})
                    await self._sleep(
                        self.recovery_config.request_pause_sec
                        if sent
                        else self.recovery_config.scan_interval_sec
                    )
                except Exception as exc:
                    self.counters.failure_count += 1
                    self.counters.last_error = f"{type(exc).__name__}: {exc}"
                    log.exception("overflow recovery failed archive=%s", archive_path)
                    self._write_status(extra={"resource_gate": health})
                    await self._sleep(self.recovery_config.scan_interval_sec)
        finally:
            self.running = False
            self._write_status()
            log.info("central sync overflow recovery stopped")

    async def _replay_one(self, archive_path: Path) -> bool:
        self.counters.archive_open_count += 1
        self.counters.last_archive_path = str(archive_path)
        store = OutboxStore(
            str(archive_path),
            max_db_size_mb=None,
            min_free_space_mb=0,
            required_mount_path=None,
            fail_if_mount_missing=False,
        )
        try:
            replay_cfg = self.config.model_copy(deep=True)
            replay_cfg.status_file = self.recovery_config.uploader_status_file
            replay_cfg.uploader.max_messages_per_request = (
                self.recovery_config.max_messages_per_request
            )
            replay_cfg.uploader.max_request_bytes = self.recovery_config.max_request_bytes
            replay_cfg.uploader.fair_batching_enabled = False
            replay_cfg.uploader.status_interval_sec = max(
                1.0, self.recovery_config.request_pause_sec
            )
            replay_cfg.outbox.acked_retention_hours = 0

            uploader = CentralSyncUploader(
                config=replay_cfg,
                outbox=store,
                client=self.client,
                transport_lock=self.transport_lock,
            )
            self.counters.request_cycle_count += 1
            self.counters.last_request_utc = utc_now_iso()
            sent = await uploader.run_once()
            if sent and uploader.counters.request_success_count > 0:
                self.counters.last_success_utc = utc_now_iso()

            await asyncio.to_thread(
                store.cleanup,
                acked_retention_hours=0,
                dead_letter_retention_days=self.config.outbox.dead_letter_retention_days,
                transport_attempt_retention_days=(
                    self.config.outbox.transport_attempt_retention_days
                ),
            )
            stats = await asyncio.to_thread(store.stats, 0)
            remaining = int(stats.get("unacked_count", 0))
            dead = int(stats.get("dead_count", 0))
        finally:
            store.close()

        if remaining == 0:
            # Never auto-delete recovery evidence. Persist a marker keyed to the
            # DB's current size/mtime. If the archiver later appends to the same
            # hourly DB, the marker becomes stale and replay resumes.
            self._write_replayed_marker(archive_path, dead_count=dead)
            self.counters.archive_drained_count += 1
            self.counters.retained_drained_count += 1
            log.info(
                "overflow archive fully replayed and retained path=%s dead=%s",
                archive_path,
                dead,
            )
        return sent

    def _resource_gate(self) -> tuple[bool, str | None, dict[str, Any]]:
        live = self.live_probe.snapshot()
        mem_mb = _mem_available_mb()
        try:
            load1 = float(os.getloadavg()[0])
        except Exception:
            load1 = 0.0

        paused = self.pause.is_paused()
        health = {
            "transport_paused": paused,
            "live": live,
            "mem_available_mb": mem_mb,
            "load1": round(load1, 3),
        }

        if paused:
            self.counters.pause_transport_count += 1
            return False, "transport_paused", health
        if not live.get("available"):
            self.counters.pause_live_count += 1
            return False, str(live.get("reason") or "live_outbox_unavailable"), health

        count = int(live.get("unacked_count") or 0)
        age = live.get("oldest_age_sec")
        if count > self.recovery_config.live_pause_sendable_count:
            self.counters.pause_live_count += 1
            return False, f"live_unacked_count={count}", health
        if age is not None and float(age) > self.recovery_config.live_pause_oldest_age_sec:
            self.counters.pause_live_count += 1
            return False, f"live_oldest_age_sec={float(age):.1f}", health
        if mem_mb < self.recovery_config.min_available_memory_mb:
            self.counters.pause_memory_count += 1
            return False, f"mem_available_mb={mem_mb}", health
        if load1 > self.recovery_config.max_load1:
            self.counters.pause_load_count += 1
            return False, f"load1={load1:.2f}", health
        return True, None, health

    def _next_archive(self) -> Path | None:
        root = Path(self.recovery_config.archive_dir)
        if not root.exists():
            return None
        candidates = sorted(
            [p for p in root.glob(self.recovery_config.archive_glob) if p.is_file()],
            key=lambda p: (p.stat().st_mtime, p.name),
        )
        for path in candidates:
            marker = self._read_replayed_marker(path)
            signature = self._archive_signature(path)
            if marker and marker.get("signature") == signature:
                continue
            try:
                uri = f"file:{path}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, timeout=1.0)
                row = conn.execute(
                    """SELECT COUNT(*) FROM outbox_messages
                       WHERE state IN ('pending','retry','inflight')"""
                ).fetchone()
                dead = conn.execute(
                    "SELECT COUNT(*) FROM outbox_messages WHERE state='dead'"
                ).fetchone()
                conn.close()
                remaining = int(row[0] or 0) if row else 0
                dead_count = int(dead[0] or 0) if dead else 0
            except Exception:
                continue
            if remaining > 0:
                return path
            self._write_replayed_marker(path, dead_count=dead_count)
        return None

    def _marker_path(self, archive_path: Path) -> Path:
        return Path(str(archive_path) + self.recovery_config.marker_suffix)

    def _read_replayed_marker(self, archive_path: Path) -> dict[str, Any] | None:
        marker = self._marker_path(archive_path)
        try:
            value = json.loads(marker.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except Exception:
            return None

    def _archive_signature(self, archive_path: Path) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for label, candidate in (
            ("db", archive_path),
            ("wal", Path(str(archive_path) + "-wal")),
            ("shm", Path(str(archive_path) + "-shm")),
        ):
            try:
                stat = candidate.stat()
                result[label] = {
                    "size": int(stat.st_size),
                    "mtime_ns": int(stat.st_mtime_ns),
                }
            except FileNotFoundError:
                result[label] = None
        return result

    def _write_replayed_marker(self, archive_path: Path, *, dead_count: int) -> None:
        if not archive_path.exists():
            return
        payload = {
            "archive_path": str(archive_path),
            "signature": self._archive_signature(archive_path),
            "dead_count": int(dead_count),
            "completed_utc": utc_now_iso(),
            "archive_retained": True,
        }
        safe_write_json(str(self._marker_path(archive_path)), payload)

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=max(0.2, float(seconds)))
        except asyncio.TimeoutError:
            pass

    def status(self, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        result = {
            "enabled": self.recovery_config.enabled,
            "running": self.running,
            "started_utc": self.started_utc,
            "archive_dir": self.recovery_config.archive_dir,
            "archive_glob": self.recovery_config.archive_glob,
            "archive_retention": "retain_with_replayed_marker",
            "batch_messages": self.recovery_config.max_messages_per_request,
            "batch_bytes": self.recovery_config.max_request_bytes,
            "counters": self.counters.__dict__.copy(),
            "status_generated_utc": utc_now_iso(),
        }
        if extra:
            result.update(extra)
        return result

    def _write_status(self, *, extra: dict[str, Any] | None = None) -> None:
        try:
            safe_write_json(self.recovery_config.status_file, self.status(extra=extra))
        except Exception as exc:
            log.warning("failed to write overflow recovery status: %s", exc)


def _mem_available_mb() -> int:
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 0
