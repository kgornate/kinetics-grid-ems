from __future__ import annotations

# CENTRAL_SYNC_G41_RELIABILITY_V1
import json
import os
import sqlite3
import shutil
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .contracts import LogicalMessage


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class OutboxItem:
    message_id: str
    stream: str
    substream: str
    sequence: int
    priority: str
    priority_rank: int
    created_at_utc: str
    created_epoch: float
    payload_json: str
    payload_bytes: int
    attempt_count: int
    next_attempt_epoch: float
    last_attempt_utc: str | None
    last_error: str | None
    state: str

    def payload(self) -> dict[str, Any]:
        return json.loads(self.payload_json)


class OutboxCapacityError(RuntimeError):
    pass


class OutboxStore:
    """Persistent Central Sync outbox and sequence state.

    The uploader is intentionally at-least-once. Messages are only removed from
    the sendable queue after an accepted/already_processed backend ACK. If the
    process dies after the backend commits but before local ACK processing, the
    same message_id is retried and backend idempotency resolves the duplicate.
    """

    def __init__(
        self,
        path: str,
        *,
        max_db_size_mb: int | None = None,
        min_free_space_mb: int = 0,
        required_mount_path: str | None = None,
        fail_if_mount_missing: bool = True,
    ) -> None:
        self.path = Path(path)
        self.max_db_size_mb = max_db_size_mb
        self.min_free_space_mb = max(0, int(min_free_space_mb))
        self.required_mount_path = required_mount_path
        self.fail_if_mount_missing = fail_if_mount_missing
        if required_mount_path and fail_if_mount_missing and not os.path.ismount(required_mount_path):
            raise RuntimeError(f"required outbox mount is not mounted: {required_mount_path}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._stats_cache_lock = threading.Lock()
        self._stats_cache: dict[str, Any] | None = None
        self._stats_cache_monotonic = 0.0
        self._stats_cache_ttl_sec = 5.0
        self.conn = sqlite3.connect(self.path, timeout=30.0, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # CENTRAL_SYNC_TEMP_STORE_MEMORY_V1
        #
        # SQLite may create temporary files for ORDER BY / sorting.
        # On this field image that temporary-file path caused
        # OperationalError('database or disk is full') even though the
        # persistent outbox filesystem had ample free space.
        #
        # Keep only SQLite temporary working data in memory.
        # The actual outbox database remains persistent on /mnt/ems-logs.
        self.conn.execute("PRAGMA temp_store=MEMORY")
        self.conn.execute("PRAGMA busy_timeout=30000")
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=FULL")
        except Exception:
            pass
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sequences (
                    stream TEXT NOT NULL,
                    substream TEXT NOT NULL DEFAULT '',
                    last_sequence INTEGER NOT NULL,
                    updated_utc TEXT NOT NULL,
                    PRIMARY KEY(stream, substream)
                );

                CREATE TABLE IF NOT EXISTS outbox_messages (
                    message_id TEXT PRIMARY KEY,
                    gateway_id TEXT NOT NULL,
                    site_id TEXT NOT NULL,
                    stream TEXT NOT NULL,
                    substream TEXT NOT NULL DEFAULT '',
                    sequence INTEGER NOT NULL,
                    priority TEXT NOT NULL,
                    priority_rank INTEGER NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    created_epoch REAL NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_bytes INTEGER NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_epoch REAL NOT NULL DEFAULT 0,
                    last_attempt_utc TEXT,
                    last_error TEXT,
                    acknowledged_utc TEXT,
                    ack_status TEXT,
                    backend_detail TEXT,
                    UNIQUE(gateway_id, stream, substream, sequence)
                );
                CREATE INDEX IF NOT EXISTS idx_outbox_sendable
                    ON outbox_messages(state, next_attempt_epoch, priority_rank, created_epoch);
                CREATE INDEX IF NOT EXISTS idx_outbox_stream
                    ON outbox_messages(stream, substream, created_epoch);

                CREATE TABLE IF NOT EXISTS transport_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    attempted_utc TEXT NOT NULL,
                    message_count INTEGER NOT NULL,
                    payload_bytes INTEGER NOT NULL,
                    http_status INTEGER,
                    outcome TEXT NOT NULL,
                    detail TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_transport_attempts_time
                    ON transport_attempts(attempted_utc);
                """
            )
            self.conn.commit()

    def next_sequence(self, stream: str, substream: str | None = None) -> int:
        key = substream or ""
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                row = self.conn.execute(
                    "SELECT last_sequence FROM sequences WHERE stream=? AND substream=?",
                    (stream, key),
                ).fetchone()
                nxt = (int(row["last_sequence"]) + 1) if row else 1
                self.conn.execute(
                    """INSERT INTO sequences(stream,substream,last_sequence,updated_utc)
                       VALUES(?,?,?,?)
                       ON CONFLICT(stream,substream) DO UPDATE SET
                         last_sequence=excluded.last_sequence,
                         updated_utc=excluded.updated_utc""",
                    (stream, key, nxt, _utc_now()),
                )
                self.conn.commit()
                return nxt
            except Exception:
                self.conn.rollback()
                raise

    def current_sequence(self, stream: str, substream: str | None = None) -> int:
        key = substream or ""
        with self._lock:
            row = self.conn.execute(
                "SELECT last_sequence FROM sequences WHERE stream=? AND substream=?",
                (stream, key),
            ).fetchone()
            return int(row["last_sequence"]) if row else 0

    def enqueue(self, message: LogicalMessage) -> bool:
        capacity = self.capacity_status()
        if not capacity["can_accept"]:
            raise OutboxCapacityError("; ".join(capacity["reasons"]))
        payload_json = json.dumps(message.model_dump(mode="json"), separators=(",", ":"), ensure_ascii=False)
        payload_bytes = len(payload_json.encode("utf-8"))
        created_epoch = _iso_to_epoch(message.created_at_utc)
        with self._lock:
            try:
                self.conn.execute(
                    """INSERT INTO outbox_messages(
                        message_id,gateway_id,site_id,stream,substream,sequence,
                        priority,priority_rank,created_at_utc,created_epoch,
                        payload_json,payload_bytes,state,next_attempt_epoch
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0)""",
                    (
                        message.message_id,
                        message.gateway_id,
                        message.site_id,
                        message.stream,
                        message.substream or "",
                        message.sequence,
                        message.priority,
                        message.priority_rank,
                        message.created_at_utc,
                        created_epoch,
                        payload_json,
                        payload_bytes,
                        "pending",
                    ),
                )
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                # Same message_id or same stream/substream/sequence is already durable.
                return False

    def eligible(
        self,
        *,
        now_epoch: float,
        coalescing_window_sec: float,
        max_messages: int,
        max_bytes: int,
    ) -> list[OutboxItem]:
        coalesce_cutoff = now_epoch - max(0.0, coalescing_window_sec)
        with self._lock:
            rows = self.conn.execute(
                """SELECT * FROM outbox_messages
                   WHERE state IN ('pending','retry')
                     AND next_attempt_epoch <= ?
                     AND (priority_rank <= 1 OR created_epoch <= ?)
                   ORDER BY priority_rank ASC, created_epoch ASC, message_id ASC
                   LIMIT ?""",
                (now_epoch, coalesce_cutoff, max(max_messages * 4, max_messages)),
            ).fetchall()
        selected: list[OutboxItem] = []
        total = 0
        for row in rows:
            item = _row_to_item(row)
            projected = total + item.payload_bytes
            if selected and projected > max_bytes:
                break
            if not selected and item.payload_bytes > max_bytes:
                # Allow one oversized logical message to reach transport where a 413 can
                # be recorded explicitly instead of blocking every later message forever.
                selected.append(item)
                break
            selected.append(item)
            total = projected
            if len(selected) >= max_messages:
                break
        return selected

    def mark_accepted(self, message_id: str, ack_status: str, detail: str | None = None) -> None:
        with self._lock:
            self.conn.execute(
                """UPDATE outbox_messages SET state='acked',acknowledged_utc=?,ack_status=?,
                   backend_detail=?,last_error=NULL WHERE message_id=?""",
                (_utc_now(), ack_status, detail, message_id),
            )
            self.conn.commit()

    def mark_retry(
        self,
        message_id: str,
        *,
        next_attempt_epoch: float,
        error: str,
        attempted_utc: str | None = None,
    ) -> None:
        with self._lock:
            self.conn.execute(
                """UPDATE outbox_messages SET state='retry',attempt_count=attempt_count+1,
                   next_attempt_epoch=?,last_attempt_utc=?,last_error=? WHERE message_id=?""",
                (next_attempt_epoch, attempted_utc or _utc_now(), error[:2000], message_id),
            )
            self.conn.commit()

    def mark_dead(self, message_id: str, *, error: str, detail: str | None = None) -> None:
        with self._lock:
            self.conn.execute(
                """UPDATE outbox_messages SET state='dead',attempt_count=attempt_count+1,
                   last_attempt_utc=?,last_error=?,backend_detail=? WHERE message_id=?""",
                (_utc_now(), error[:2000], detail, message_id),
            )
            self.conn.commit()

    def apply_batch_updates(
        self,
        *,
        accepted: Iterable[tuple[str, str, str | None]] = (),
        retries: Iterable[tuple[str, float, str, str | None]] = (),
        dead: Iterable[tuple[str, str, str | None]] = (),
    ) -> dict[str, int]:
        """Apply all per-message delivery results in one durable transaction."""
        accepted_rows = list(accepted)
        retry_rows = list(retries)
        dead_rows = list(dead)
        if not accepted_rows and not retry_rows and not dead_rows:
            return {"accepted": 0, "retry": 0, "dead": 0}

        acked_utc = _utc_now()
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                if accepted_rows:
                    self.conn.executemany(
                        """UPDATE outbox_messages
                           SET state='acked',acknowledged_utc=?,ack_status=?,
                               backend_detail=?,last_error=NULL
                           WHERE message_id=?""",
                        [(acked_utc, status, detail, message_id)
                         for message_id, status, detail in accepted_rows],
                    )
                if retry_rows:
                    self.conn.executemany(
                        """UPDATE outbox_messages
                           SET state='retry',attempt_count=attempt_count+1,
                               next_attempt_epoch=?,last_attempt_utc=?,last_error=?
                           WHERE message_id=?""",
                        [(next_epoch, attempted_utc or acked_utc, error[:2000], message_id)
                         for message_id, next_epoch, error, attempted_utc in retry_rows],
                    )
                if dead_rows:
                    self.conn.executemany(
                        """UPDATE outbox_messages
                           SET state='dead',attempt_count=attempt_count+1,
                               last_attempt_utc=?,last_error=?,backend_detail=?
                           WHERE message_id=?""",
                        [(acked_utc, error[:2000], detail, message_id)
                         for message_id, error, detail in dead_rows],
                    )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

        return {
            "accepted": len(accepted_rows),
            "retry": len(retry_rows),
            "dead": len(dead_rows),
        }

    def record_attempt(
        self,
        *,
        request_id: str,
        message_count: int,
        payload_bytes: int,
        http_status: int | None,
        outcome: str,
        detail: str | None = None,
    ) -> None:
        with self._lock:
            self.conn.execute(
                """INSERT INTO transport_attempts(request_id,attempted_utc,message_count,
                   payload_bytes,http_status,outcome,detail) VALUES(?,?,?,?,?,?,?)""",
                (request_id, _utc_now(), message_count, payload_bytes, http_status, outcome, detail),
            )
            self.conn.commit()

    def sqlite_space_status(self) -> dict[str, int]:
        """Return physical and reusable SQLite space without scanning payload rows.

        max_db_size_mb is enforced against live main-database pages rather than
        the raw main DB file size. SQLite freelist pages are already reusable and
        must not trigger a false capacity-full condition after ACK cleanup. WAL
        usage is reported separately and constrained by the filesystem free-space
        guard rather than double-counted against the logical outbox capacity.
        """
        with self._lock:
            try:
                page_size = int(self.conn.execute("PRAGMA page_size").fetchone()[0])
                page_count = int(self.conn.execute("PRAGMA page_count").fetchone()[0])
                freelist_count = int(self.conn.execute("PRAGMA freelist_count").fetchone()[0])
            except Exception:
                page_size = 0
                page_count = 0
                freelist_count = 0

        main_db_bytes = self.path.stat().st_size if self.path.exists() else 0
        wal_path = Path(str(self.path) + "-wal")
        shm_path = Path(str(self.path) + "-shm")
        wal_bytes = wal_path.stat().st_size if wal_path.exists() else 0
        shm_bytes = shm_path.stat().st_size if shm_path.exists() else 0

        if page_size > 0 and page_count >= freelist_count:
            used_page_bytes = (page_count - freelist_count) * page_size
            reusable_page_bytes = freelist_count * page_size
            # Capacity is based on live main-database pages. WAL is transient
            # and separately protected by the filesystem free-space guard.
            logical_used_bytes = used_page_bytes
        else:
            used_page_bytes = main_db_bytes
            reusable_page_bytes = 0
            logical_used_bytes = main_db_bytes

        return {
            "page_size": page_size,
            "page_count": page_count,
            "freelist_count": freelist_count,
            "main_db_bytes": int(main_db_bytes),
            "wal_bytes": int(wal_bytes),
            "shm_bytes": int(shm_bytes),
            "physical_total_bytes": int(main_db_bytes + wal_bytes + shm_bytes),
            "used_page_bytes": int(used_page_bytes),
            "reusable_page_bytes": int(reusable_page_bytes),
            "logical_used_bytes": int(logical_used_bytes),
        }

    def capacity_status(self) -> dict[str, Any]:
        space = self.sqlite_space_status()
        used_bytes = int(space["logical_used_bytes"])
        reasons: list[str] = []
        max_bytes = None
        if self.max_db_size_mb is not None and self.max_db_size_mb > 0:
            max_bytes = int(self.max_db_size_mb) * 1024 * 1024
            if used_bytes >= max_bytes:
                reasons.append(
                    f"outbox logical used space reached max size {self.max_db_size_mb} MB"
                )
        if self.required_mount_path and self.fail_if_mount_missing and not os.path.ismount(self.required_mount_path):
            reasons.append(f"required outbox mount is not mounted: {self.required_mount_path}")
        try:
            usage = shutil.disk_usage(self.path.parent)
            free_mb = int(usage.free // (1024 * 1024))
            if free_mb < self.min_free_space_mb:
                reasons.append(f"outbox filesystem free space {free_mb} MB below minimum {self.min_free_space_mb} MB")
        except Exception:
            free_mb = None
        return {
            "can_accept": not reasons,
            "reasons": reasons,
            "db_size_bytes": space["physical_total_bytes"],
            "logical_used_bytes": used_bytes,
            "reusable_page_bytes": space["reusable_page_bytes"],
            "wal_bytes": space["wal_bytes"],
            "max_db_size_bytes": max_bytes,
            "filesystem_free_mb": free_mb,
            "min_free_space_mb": self.min_free_space_mb,
        }

    def stats(self, max_age_sec: float | None = None) -> dict[str, Any]:
        ttl = self._stats_cache_ttl_sec if max_age_sec is None else max(0.0, float(max_age_sec))
        now_mono = time.monotonic()
        with self._stats_cache_lock:
            if (
                self._stats_cache is not None
                and ttl > 0
                and now_mono - self._stats_cache_monotonic <= ttl
            ):
                return dict(self._stats_cache)

        now = time.time()
        with self._lock:
            by_state = {
                row["state"]: int(row["n"])
                for row in self.conn.execute(
                    "SELECT state,COUNT(*) AS n FROM outbox_messages GROUP BY state"
                ).fetchall()
            }
            by_priority = {
                row["priority"]: int(row["n"])
                for row in self.conn.execute(
                    """SELECT priority,COUNT(*) AS n FROM outbox_messages
                       WHERE state IN ('pending','retry') GROUP BY priority"""
                ).fetchall()
            }
            row = self.conn.execute(
                """SELECT MIN(created_epoch) AS oldest,COALESCE(SUM(payload_bytes),0) AS bytes
                   FROM outbox_messages WHERE state IN ('pending','retry')"""
            ).fetchone()
            dead = self.conn.execute(
                "SELECT COUNT(*) AS n FROM outbox_messages WHERE state='dead'"
            ).fetchone()["n"]
        oldest = row["oldest"] if row else None
        space = self.sqlite_space_status()
        result = {
            "path": str(self.path),
            "db_size_bytes": space["physical_total_bytes"],
            "logical_used_bytes": space["logical_used_bytes"],
            "reusable_page_bytes": space["reusable_page_bytes"],
            "wal_bytes": space["wal_bytes"],
            "sendable_count": by_state.get("pending", 0) + by_state.get("retry", 0),
            "pending_count": by_state.get("pending", 0),
            "retry_count": by_state.get("retry", 0),
            "acked_count": by_state.get("acked", 0),
            "dead_count": int(dead or 0),
            "sendable_bytes": int(row["bytes"] if row else 0),
            "oldest_sendable_age_sec": round(max(0.0, now - float(oldest)), 3) if oldest else None,
            "by_priority": by_priority,
            "capacity": self.capacity_status(),
        }
        with self._stats_cache_lock:
            self._stats_cache = dict(result)
            self._stats_cache_monotonic = now_mono
        return result

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                """SELECT message_id,stream,substream,sequence,priority,state,attempt_count,
                   created_at_utc,last_attempt_utc,last_error,acknowledged_utc,ack_status
                   FROM outbox_messages ORDER BY created_epoch DESC LIMIT ?""",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def cleanup(
        self,
        *,
        acked_retention_hours: int,
        dead_letter_retention_days: int,
        transport_attempt_retention_days: int,
    ) -> dict[str, int]:
        now = time.time()
        acked_cutoff = datetime.fromtimestamp(
            now - max(0, acked_retention_hours) * 3600, timezone.utc
        ).isoformat().replace("+00:00", "Z")
        dead_cutoff = datetime.fromtimestamp(
            now - max(0, dead_letter_retention_days) * 86400, timezone.utc
        ).isoformat().replace("+00:00", "Z")
        attempt_cutoff = datetime.fromtimestamp(
            now - max(0, transport_attempt_retention_days) * 86400,
            timezone.utc,
        ).isoformat().replace("+00:00", "Z")
        with self._lock:
            a = self.conn.execute(
                "DELETE FROM outbox_messages WHERE state='acked' AND acknowledged_utc < ?",
                (acked_cutoff,),
            ).rowcount
            d = self.conn.execute(
                "DELETE FROM outbox_messages WHERE state='dead' AND last_attempt_utc < ?",
                (dead_cutoff,),
            ).rowcount
            t = self.conn.execute(
                "DELETE FROM transport_attempts WHERE attempted_utc < ?",
                (attempt_cutoff,),
            ).rowcount
            self.conn.commit()
            try:
                self.conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except Exception:
                pass

        return {
            "acked_deleted": int(a),
            "dead_deleted": int(d),
            "transport_attempts_deleted": int(t),
        }

    def db_size_bytes(self) -> int:
        total = 0
        for p in [self.path, Path(str(self.path) + "-wal"), Path(str(self.path) + "-shm")]:
            if p.exists():
                total += p.stat().st_size
        return total

    def close(self) -> None:
        with self._lock:
            self.conn.close()


def _iso_to_epoch(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return time.time()


def _row_to_item(row: sqlite3.Row) -> OutboxItem:
    return OutboxItem(
        message_id=row["message_id"],
        stream=row["stream"],
        substream=row["substream"],
        sequence=int(row["sequence"]),
        priority=row["priority"],
        priority_rank=int(row["priority_rank"]),
        created_at_utc=row["created_at_utc"],
        created_epoch=float(row["created_epoch"]),
        payload_json=row["payload_json"],
        payload_bytes=int(row["payload_bytes"]),
        attempt_count=int(row["attempt_count"]),
        next_attempt_epoch=float(row["next_attempt_epoch"]),
        last_attempt_utc=row["last_attempt_utc"],
        last_error=row["last_error"],
        state=row["state"],
    )
