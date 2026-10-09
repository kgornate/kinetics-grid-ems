from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import CentralBackendClient
from .config import CentralSyncConfig, load_central_sync_config
from .outbox import OutboxStore
from .status import safe_write_json, utc_now_iso
from .uploader import CentralSyncUploader

log = logging.getLogger(__name__)


@dataclass
class ReplayCounters:
    scan_count: int = 0
    request_cycle_count: int = 0
    pause_live_count: int = 0
    pause_memory_count: int = 0
    pause_load_count: int = 0
    archive_open_count: int = 0
    archive_drained_count: int = 0
    failure_count: int = 0
    last_archive_path: str | None = None
    last_request_utc: str | None = None
    last_success_utc: str | None = None
    last_pause_reason: str | None = None
    last_error: str | None = None


class LiveOutboxProbe:
    """Read-only health probe; never changes live uploader state."""

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


class BacklogReplayService:
    """Resource-bounded historical replay that always yields to live traffic."""

    def __init__(self, config: CentralSyncConfig) -> None:
        self.config = config
        self.replay_config = config.backlog_replay
        self.live_probe = LiveOutboxProbe(config.outbox.path)
        self.client = CentralBackendClient(config.backend, config.identity.gateway_id)
        self.counters = ReplayCounters()
        self.started_utc = utc_now_iso()
        self.running = False
        self._stop = asyncio.Event()

    async def stop(self) -> None:
        self._stop.set()

    async def close(self) -> None:
        await self.client.close()

    async def run_forever(self) -> None:
        if not self.replay_config.enabled:
            log.info("central sync backlog replay disabled")
            self._write_status()
            return
        self.running = True
        self._stop.clear()
        log.info(
            "central sync backlog replay started dir=%s batch=%s bytes=%s pause=%.1fs",
            self.replay_config.archive_dir,
            self.replay_config.max_messages_per_request,
            self.replay_config.max_request_bytes,
            self.replay_config.request_pause_sec,
        )
        try:
            while not self._stop.is_set():
                self.counters.scan_count += 1
                allowed, reason, health = await asyncio.to_thread(self._resource_gate)
                if not allowed:
                    self.counters.last_pause_reason = reason
                    self._write_status(extra={"resource_gate": health})
                    await self._sleep(self.replay_config.scan_interval_sec)
                    continue

                archive_path = await asyncio.to_thread(self._next_archive)
                if archive_path is None:
                    self.counters.last_pause_reason = "no_backlog"
                    self._write_status(extra={"resource_gate": health})
                    await self._sleep(self.replay_config.scan_interval_sec)
                    continue

                try:
                    sent = await self._replay_one(archive_path)
                    self.counters.last_pause_reason = None
                    self.counters.last_error = None
                    self._write_status(extra={"resource_gate": health})
                    await self._sleep(
                        self.replay_config.request_pause_sec if sent
                        else self.replay_config.scan_interval_sec
                    )
                except Exception as exc:
                    self.counters.failure_count += 1
                    self.counters.last_error = f"{type(exc).__name__}: {exc}"
                    log.exception("backlog replay failed archive=%s", archive_path)
                    self._write_status(extra={"resource_gate": health})
                    await self._sleep(self.replay_config.scan_interval_sec)
        finally:
            self.running = False
            self._write_status()
            log.info("central sync backlog replay stopped")

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
            replay_cfg.status_file = self.replay_config.status_file
            replay_cfg.uploader.max_messages_per_request = self.replay_config.max_messages_per_request
            replay_cfg.uploader.max_request_bytes = self.replay_config.max_request_bytes
            replay_cfg.uploader.status_interval_sec = max(1.0, self.replay_config.request_pause_sec)
            replay_cfg.outbox.acked_retention_hours = 0

            uploader = CentralSyncUploader(
                config=replay_cfg,
                outbox=store,
                client=self.client,
            )
            self.counters.request_cycle_count += 1
            self.counters.last_request_utc = utc_now_iso()
            sent = await uploader.run_once()
            if sent and uploader.counters.request_success_count > 0:
                self.counters.last_success_utc = utc_now_iso()

            # Keep the archive small without VACUUM. When fully drained the
            # complete DB file is removed, returning physical storage at once.
            await asyncio.to_thread(
                store.cleanup,
                acked_retention_hours=0,
                dead_letter_retention_days=self.config.outbox.dead_letter_retention_days,
                transport_attempt_retention_days=self.config.outbox.transport_attempt_retention_days,
            )
            stats = await asyncio.to_thread(store.stats, 0)
            remaining = int(stats.get("unacked_count", 0))
            dead = int(stats.get("dead_count", 0))
        finally:
            store.close()

        if remaining == 0 and dead == 0 and self.replay_config.delete_drained_archives:
            self._delete_archive_files(archive_path)
            self.counters.archive_drained_count += 1
            log.info("backlog archive fully replayed and removed: %s", archive_path)
        return sent

    def _resource_gate(self) -> tuple[bool, str | None, dict[str, Any]]:
        live = self.live_probe.snapshot()
        mem_mb = _mem_available_mb()
        try:
            load1 = float(os.getloadavg()[0])
        except Exception:
            load1 = 0.0

        health = {"live": live, "mem_available_mb": mem_mb, "load1": round(load1, 3)}

        if not live.get("available"):
            self.counters.pause_live_count += 1
            return False, str(live.get("reason") or "live_outbox_unavailable"), health

        count = int(live.get("unacked_count") or 0)
        age = live.get("oldest_age_sec")
        if count > self.replay_config.live_pause_sendable_count:
            self.counters.pause_live_count += 1
            return False, f"live_unacked_count={count}", health
        if age is not None and float(age) > self.replay_config.live_pause_oldest_age_sec:
            self.counters.pause_live_count += 1
            return False, f"live_oldest_age_sec={float(age):.1f}", health
        if mem_mb < self.replay_config.min_available_memory_mb:
            self.counters.pause_memory_count += 1
            return False, f"mem_available_mb={mem_mb}", health
        if load1 > self.replay_config.max_load1:
            self.counters.pause_load_count += 1
            return False, f"load1={load1:.2f}", health
        return True, None, health

    def _next_archive(self) -> Path | None:
        root = Path(self.replay_config.archive_dir)
        if not root.exists():
            return None
        candidates = sorted(
            [p for p in root.glob("*.db") if p.is_file()],
            key=lambda p: (p.stat().st_mtime, p.name),
        )
        for path in candidates:
            # Fast read-only check avoids repeatedly opening already-empty DBs.
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
            if remaining == 0 and dead_count == 0 and self.replay_config.delete_drained_archives:
                self._delete_archive_files(path)
                self.counters.archive_drained_count += 1
        return None

    def _delete_archive_files(self, path: Path) -> None:
        for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
            try:
                candidate.unlink(missing_ok=True)
            except Exception as exc:
                log.warning("failed to remove drained archive file %s: %s", candidate, exc)

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=max(0.2, float(seconds)))
        except asyncio.TimeoutError:
            pass

    def status(self, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        result = {
            "enabled": self.replay_config.enabled,
            "running": self.running,
            "started_utc": self.started_utc,
            "archive_dir": self.replay_config.archive_dir,
            "batch_messages": self.replay_config.max_messages_per_request,
            "batch_bytes": self.replay_config.max_request_bytes,
            "counters": self.counters.__dict__.copy(),
            "status_generated_utc": utc_now_iso(),
        }
        if extra:
            result.update(extra)
        return result

    def _write_status(self, *, extra: dict[str, Any] | None = None) -> None:
        try:
            safe_write_json(self.replay_config.status_file, self.status(extra=extra))
        except Exception as exc:
            log.warning("failed to write backlog replay status: %s", exc)


def _mem_available_mb() -> int:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ornate Central Sync low-priority backlog replayer")
    parser.add_argument("--config", default="configs/central_sync.json")
    parser.add_argument("--once", action="store_true", help="Run at most one replay cycle")
    parser.add_argument("--status", action="store_true", help="Print replay status")
    return parser.parse_args()


async def amain() -> int:
    args = parse_args()
    config = load_central_sync_config(args.config)
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    service = BacklogReplayService(config)
    try:
        if args.status:
            import json
            print(json.dumps(service.status(extra={"resource_gate": service._resource_gate()[2]}), indent=2))
            return 0
        if not config.backlog_replay.enabled:
            print(f"Backlog replay disabled by config: {args.config}")
            return 0
        if args.once:
            allowed, reason, _ = await asyncio.to_thread(service._resource_gate)
            if not allowed:
                print(f"Backlog replay paused: {reason}")
                return 0
            path = await asyncio.to_thread(service._next_archive)
            if path is None:
                print("No backlog archive ready")
                return 0
            await service._replay_one(path)
            return 0

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(service.stop()))
            except NotImplementedError:
                pass
        await service.run_forever()
        return 0
    finally:
        await service.close()


def main() -> None:
    raise SystemExit(asyncio.run(amain()))


if __name__ == "__main__":
    main()
