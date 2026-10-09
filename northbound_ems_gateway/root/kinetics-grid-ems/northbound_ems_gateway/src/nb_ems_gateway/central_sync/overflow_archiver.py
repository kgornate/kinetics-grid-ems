from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import CentralSyncConfig
from .outbox import OutboxStore
from .status import safe_write_json, utc_now_iso

log = logging.getLogger(__name__)


@dataclass
class OverflowArchiverCounters:
    check_count: int = 0
    spill_cycle_count: int = 0
    archived_message_count: int = 0
    archived_payload_bytes: int = 0
    source_deleted_count: int = 0
    duplicate_archive_count: int = 0
    no_candidate_count: int = 0
    disk_pause_count: int = 0
    failure_count: int = 0
    last_check_utc: str | None = None
    last_spill_utc: str | None = None
    last_archive_path: str | None = None
    last_trigger: str | None = None
    last_error: str | None = None


class OverflowArchiver:
    """Move old unsent live rows into bounded historical archive segments.

    G6.1 keeps two independent protections around the live lane:

    * size trigger: spill when logical live DB usage crosses the configured
      high watermark, returning toward the target watermark;
    * age trigger: even below the size watermark, spill rows older than
      ``spill_min_age_sec`` so current telemetry cannot sit behind minutes or
      hours of historical data.

    Archive writes are also blocked when filesystem free space falls below the
    archive reserve.  In that case the normal live-outbox hard capacity guard
    remains the final bounded fail-safe rather than filling the filesystem.

    Copy-before-delete keeps archival at-least-once.  Rows claimed ``inflight``
    by the live uploader are never moved.
    """

    def __init__(self, *, config: CentralSyncConfig, outbox: OutboxStore) -> None:
        self.config = config
        self.archive_config = config.overflow_archive
        self.outbox = outbox
        self.counters = OverflowArchiverCounters()
        self.started_utc = utc_now_iso()
        self.running = False
        self._stop = asyncio.Event()

    async def stop(self) -> None:
        self._stop.set()

    async def close(self) -> None:
        return None

    async def run_forever(self) -> None:
        if not self.archive_config.enabled:
            log.info("central sync overflow archiver disabled")
            return
        self.running = True
        self._stop.clear()
        log.info(
            "central sync overflow archiver started high=%sMB target=%sMB age=%ss archive_free_reserve=%sMB dir=%s",
            self.archive_config.high_watermark_mb,
            self.archive_config.target_watermark_mb,
            self.archive_config.spill_min_age_sec,
            self.archive_config.min_archive_free_space_mb,
            self.archive_config.archive_dir,
        )
        try:
            while not self._stop.is_set():
                try:
                    await asyncio.to_thread(self.run_once)
                except Exception as exc:
                    self.counters.failure_count += 1
                    self.counters.last_error = f"{type(exc).__name__}: {exc}"
                    log.exception("central sync overflow archiver cycle failed")
                    self._write_status()
                try:
                    await asyncio.wait_for(
                        self._stop.wait(),
                        timeout=max(0.2, float(self.archive_config.check_interval_sec)),
                    )
                except asyncio.TimeoutError:
                    pass
        finally:
            self.running = False
            self._write_status()
            log.info("central sync overflow archiver stopped")

    def run_once(self) -> dict[str, Any]:
        cfg = self.archive_config
        self.counters.check_count += 1
        self.counters.last_check_utc = utc_now_iso()

        now = time.time()
        space = self.outbox.sqlite_space_status()
        used = int(space["logical_used_bytes"])
        high = int(cfg.high_watermark_mb) * 1024 * 1024
        target = int(cfg.target_watermark_mb) * 1024 * 1024
        oldest_age = self.outbox.oldest_spillable_age_sec(now)

        if target >= high:
            raise ValueError("overflow target_watermark_mb must be smaller than high_watermark_mb")

        size_trigger = used >= high
        age_trigger = oldest_age is not None and oldest_age >= float(cfg.spill_min_age_sec)

        if not size_trigger and not age_trigger:
            self.counters.last_trigger = None
            self.counters.last_error = None
            self._write_status()
            return {
                "spilled": False,
                "reason": "live_window_healthy",
                "logical_used_bytes": used,
                "oldest_spillable_age_sec": oldest_age,
            }

        archive_free_mb = self._archive_free_mb()
        if archive_free_mb < int(cfg.min_archive_free_space_mb):
            self.counters.disk_pause_count += 1
            self.counters.last_trigger = "size" if size_trigger else "age"
            self.counters.last_error = (
                f"archive filesystem free space {archive_free_mb} MB below reserve "
                f"{cfg.min_archive_free_space_mb} MB"
            )
            self._write_status()
            return {
                "spilled": False,
                "reason": "archive_free_space_guard",
                "archive_free_mb": archive_free_mb,
                "logical_used_bytes": used,
                "oldest_spillable_age_sec": oldest_age,
            }

        total_archived = 0
        total_deleted = 0
        total_payload = 0
        archive_path: str | None = None
        trigger_names: list[str] = []
        if size_trigger:
            trigger_names.append("size")
        if age_trigger:
            trigger_names.append("age")
        self.counters.last_trigger = "+".join(trigger_names)

        chunks = 0
        while chunks < int(cfg.max_chunks_per_check):
            size_need = used > target if size_trigger else False
            age_need = oldest_age is not None and oldest_age >= float(cfg.spill_min_age_sec)
            if not size_need and not age_need:
                break

            # Recheck disk reserve before every bounded archive chunk.
            archive_free_mb = self._archive_free_mb()
            if archive_free_mb < int(cfg.min_archive_free_space_mb):
                self.counters.disk_pause_count += 1
                self.counters.last_error = (
                    f"archive filesystem free space {archive_free_mb} MB below reserve "
                    f"{cfg.min_archive_free_space_mb} MB"
                )
                break

            chunks += 1
            rows = self.outbox.spill_rows(
                now_epoch=time.time(),
                min_age_sec=cfg.spill_min_age_sec,
                max_messages=cfg.max_messages_per_cycle,
                max_bytes=cfg.max_bytes_per_cycle,
            )
            if not rows:
                self.counters.no_candidate_count += 1
                break

            archive_path = str(self._segment_path())
            archive = OutboxStore(
                archive_path,
                max_db_size_mb=None,
                min_free_space_mb=0,
                required_mount_path=None,
                fail_if_mount_missing=False,
            )
            try:
                ids = [str(row["message_id"]) for row in rows]
                inserted = archive.import_rows(rows)
                present = archive.count_message_ids(ids)
                if present != len(ids):
                    raise RuntimeError(
                        f"archive verification failed: selected={len(ids)} present={present}"
                    )
                deleted = self.outbox.delete_spilled(ids)
                payload = sum(int(row.get("payload_bytes") or 0) for row in rows)
                duplicates = max(0, len(rows) - inserted)
                total_archived += len(rows)
                total_deleted += deleted
                total_payload += payload
                self.counters.duplicate_archive_count += duplicates
            finally:
                archive.close()

            used = int(self.outbox.sqlite_space_status()["logical_used_bytes"])
            oldest_age = self.outbox.oldest_spillable_age_sec(time.time())

            if deleted == 0:
                break

        if total_archived:
            self.counters.spill_cycle_count += 1
            self.counters.archived_message_count += total_archived
            self.counters.archived_payload_bytes += total_payload
            self.counters.source_deleted_count += total_deleted
            self.counters.last_spill_utc = utc_now_iso()
            self.counters.last_archive_path = archive_path
            if not self.counters.last_error:
                self.counters.last_error = None
            log.warning(
                "central sync overflow archived trigger=%s messages=%s deleted=%s payload_mb=%.2f logical_live_mb=%.2f oldest_age_sec=%s archive=%s",
                self.counters.last_trigger,
                total_archived,
                total_deleted,
                total_payload / 1024 / 1024,
                used / 1024 / 1024,
                None if oldest_age is None else round(oldest_age, 1),
                archive_path,
            )

        self._write_status()
        return {
            "spilled": bool(total_archived),
            "trigger": self.counters.last_trigger,
            "archived_messages": total_archived,
            "source_deleted": total_deleted,
            "payload_bytes": total_payload,
            "logical_used_bytes": used,
            "oldest_spillable_age_sec": oldest_age,
            "archive_free_mb": archive_free_mb,
            "archive_path": archive_path,
        }

    def _archive_free_mb(self) -> int:
        root = Path(self.archive_config.archive_dir)
        root.mkdir(parents=True, exist_ok=True)
        return int(shutil.disk_usage(root).free // (1024 * 1024))

    def _segment_path(self) -> Path:
        root = Path(self.archive_config.archive_dir)
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H")
        return root / f"central_sync_overflow_{stamp}.db"

    def status(self) -> dict[str, Any]:
        oldest_age = None
        try:
            oldest_age = self.outbox.oldest_spillable_age_sec()
        except Exception:
            pass
        archive_free_mb = None
        try:
            archive_free_mb = self._archive_free_mb()
        except Exception:
            pass
        return {
            "enabled": self.archive_config.enabled,
            "running": self.running,
            "started_utc": self.started_utc,
            "archive_dir": self.archive_config.archive_dir,
            "high_watermark_mb": self.archive_config.high_watermark_mb,
            "target_watermark_mb": self.archive_config.target_watermark_mb,
            "spill_min_age_sec": self.archive_config.spill_min_age_sec,
            "min_archive_free_space_mb": self.archive_config.min_archive_free_space_mb,
            "oldest_spillable_age_sec": oldest_age,
            "archive_free_mb": archive_free_mb,
            "counters": self.counters.__dict__.copy(),
            "status_generated_utc": utc_now_iso(),
        }

    def _write_status(self) -> None:
        try:
            safe_write_json(self.archive_config.status_file, self.status())
        except Exception as exc:
            log.warning("failed to write overflow archiver status: %s", exc)
