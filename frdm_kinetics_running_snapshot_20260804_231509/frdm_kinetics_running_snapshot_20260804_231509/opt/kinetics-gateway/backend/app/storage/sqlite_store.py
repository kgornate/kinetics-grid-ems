from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import threading
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.config import StorageConfig, project_root


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_mount_ready(config: StorageConfig) -> bool:
    """Return True only when the preferred mount point is a real mounted filesystem."""
    mount_point = Path(config.preferred_mount_point)
    return mount_point.exists() and os.path.ismount(mount_point)


def choose_storage_root(config: StorageConfig) -> Path:
    preferred = Path(config.preferred_root)
    fallback = Path(config.fallback_root)
    if not fallback.is_absolute():
        fallback = project_root() / fallback

    mount_ready = _is_mount_ready(config)
    if config.require_preferred_mount and not mount_ready:
        raise RuntimeError(
            f"Required preferred storage is not mounted at {config.preferred_mount_point}"
        )

    candidates: list[Path] = [preferred] if mount_ready else []
    candidates.append(fallback)
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return candidate
        except OSError:
            continue
    raise RuntimeError("No writable storage location is available")


class SQLiteStore:
    def __init__(self, config: StorageConfig) -> None:
        self.config = config
        self.preferred_mount_ready = _is_mount_ready(config)
        self.root = choose_storage_root(config)
        self.database_path = self.root / config.database_name
        self.log_path = self.root / config.log_name
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._records: dict[str, int] = {}
        self._telemetry_size: dict[str, float | int] = {}
        self._initialize()
        self._load_status_counters()

    @property
    def using_preferred_storage(self) -> bool:
        return self.preferred_mount_ready and self.root == Path(self.config.preferred_root)

    @property
    def quota_bytes(self) -> int:
        quota_gb = (
            self.config.quota_gb
            if self.using_preferred_storage
            else min(self.config.quota_gb, self.config.fallback_quota_gb)
        )
        return int(quota_gb * 1024**3)

    @property
    def retention_days(self) -> int:
        return (
            self.config.telemetry_retention_days
            if self.using_preferred_storage
            else min(
                self.config.telemetry_retention_days,
                self.config.fallback_telemetry_retention_days,
            )
        )

    @property
    def sample_interval_seconds(self) -> float:
        return (
            self.config.sample_interval_seconds
            if self.using_preferred_storage
            else max(
                self.config.sample_interval_seconds,
                self.config.fallback_sample_interval_seconds,
            )
        )

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_blob BLOB,
                    encoding TEXT NOT NULL DEFAULT 'json',
                    uncompressed_bytes INTEGER,
                    stored_bytes INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_telemetry_asset_time ON telemetry(asset_id, timestamp);

                CREATE TABLE IF NOT EXISTS alarms (
                    alarm_key TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    active INTEGER NOT NULL,
                    raised_at TEXT NOT NULL,
                    cleared_at TEXT,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_alarms_active ON alarms(active, severity);

                CREATE TABLE IF NOT EXISTS alarm_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    alarm_key TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_alarm_history_time ON alarm_history(timestamp);

                CREATE TABLE IF NOT EXISTS command_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    username TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    point_key TEXT NOT NULL,
                    requested_value_json TEXT,
                    status TEXT NOT NULL,
                    response_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_command_time ON command_audit(timestamp);

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    asset_id TEXT,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_time ON events(timestamp);
                """
            )
        self._migrate_telemetry_columns()

    def _migrate_telemetry_columns(self) -> None:
        columns = {
            str(row[1]) for row in self._connection.execute("PRAGMA table_info(telemetry)").fetchall()
        }
        additions = {
            "payload_blob": "BLOB",
            "encoding": "TEXT NOT NULL DEFAULT 'json'",
            "uncompressed_bytes": "INTEGER",
            "stored_bytes": "INTEGER",
        }
        with self._connection:
            for name, definition in additions.items():
                if name not in columns:
                    self._connection.execute(f"ALTER TABLE telemetry ADD COLUMN {name} {definition}")

    def _load_status_counters(self) -> None:
        """Load record and size counters once; normal status calls use in-memory values."""
        with self._lock:
            self._records = {
                table: int(self._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in ("telemetry", "alarms", "alarm_history", "command_audit", "events")
            }
            row = self._connection.execute(
                """
                SELECT COUNT(*) AS count,
                       COALESCE(SUM(uncompressed_bytes),0) AS raw_sum,
                       COALESCE(SUM(stored_bytes),0) AS stored_sum
                FROM telemetry
                """
            ).fetchone()
            count = int(row["count"])
            raw_sum = int(row["raw_sum"])
            stored_sum = int(row["stored_sum"])
            self._telemetry_size = {
                "records": count,
                "uncompressed_bytes_total": raw_sum,
                "stored_bytes_total": stored_sum,
                "average_uncompressed_bytes": (raw_sum / count) if count else 0.0,
                "average_stored_bytes": (stored_sum / count) if count else 0.0,
            }

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _encode_payload(
        payload: dict[str, Any], compress: bool, compression_level: int = 1
    ) -> tuple[str, bytes | None, str, int, int]:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if compress:
            blob = zlib.compress(raw, level=compression_level)
            return "", blob, "zlib-json", len(raw), len(blob)
        text = raw.decode("utf-8")
        return text, None, "json", len(raw), len(raw)

    @staticmethod
    def _decode_payload(row: sqlite3.Row) -> dict[str, Any]:
        encoding = row["encoding"] if "encoding" in row.keys() else "json"
        if encoding == "zlib-json" and row["payload_blob"] is not None:
            return json.loads(zlib.decompress(row["payload_blob"]).decode("utf-8"))
        return json.loads(row["payload_json"] or "{}")

    def store_telemetry_batch(
        self,
        samples: list[tuple[str, dict[str, Any], str | None]],
    ) -> dict[str, int]:
        """Compress samples and insert them in one SQLite transaction."""
        if not samples:
            return {"records": 0, "uncompressed_bytes": 0, "stored_bytes": 0}

        rows: list[tuple[Any, ...]] = []
        raw_total = 0
        stored_total = 0
        for asset_id, payload, timestamp in samples:
            text, blob, encoding, raw_size, stored_size = self._encode_payload(
                payload,
                self.config.compress_history,
                self.config.compression_level,
            )
            rows.append(
                (
                    timestamp or utc_now(),
                    asset_id,
                    text,
                    blob,
                    encoding,
                    raw_size,
                    stored_size,
                )
            )
            raw_total += raw_size
            stored_total += stored_size

        with self._lock, self._connection:
            self._connection.executemany(
                """
                INSERT INTO telemetry(
                    timestamp, asset_id, payload_json, payload_blob, encoding,
                    uncompressed_bytes, stored_bytes
                ) VALUES(?,?,?,?,?,?,?)
                """,
                rows,
            )
            inserted = len(rows)
            self._records["telemetry"] = self._records.get("telemetry", 0) + inserted
            total_records = int(self._records["telemetry"])
            raw_sum = int(self._telemetry_size.get("uncompressed_bytes_total", 0)) + raw_total
            stored_sum = int(self._telemetry_size.get("stored_bytes_total", 0)) + stored_total
            self._telemetry_size = {
                "records": total_records,
                "uncompressed_bytes_total": raw_sum,
                "stored_bytes_total": stored_sum,
                "average_uncompressed_bytes": (raw_sum / total_records) if total_records else 0.0,
                "average_stored_bytes": (stored_sum / total_records) if total_records else 0.0,
            }

        return {
            "records": len(rows),
            "uncompressed_bytes": raw_total,
            "stored_bytes": stored_total,
        }

    def store_telemetry(
        self, asset_id: str, payload: dict[str, Any], timestamp: str | None = None
    ) -> dict[str, int]:
        result = self.store_telemetry_batch([(asset_id, payload, timestamp)])
        return {
            "uncompressed_bytes": result["uncompressed_bytes"],
            "stored_bytes": result["stored_bytes"],
        }

    def query_telemetry(self, asset_id: str, *, limit: int = 500, since: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT timestamp, asset_id, payload_json, payload_blob, encoding FROM telemetry WHERE asset_id=?"
        args: list[Any] = [asset_id]
        if since:
            sql += " AND timestamp>=?"
            args.append(since)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(max(1, min(limit, 5000)))
        with self._lock:
            rows = self._connection.execute(sql, args).fetchall()
        return [
            {"timestamp": row["timestamp"], "asset_id": row["asset_id"], "payload": self._decode_payload(row)}
            for row in rows
        ]

    def list_asset_ids(self) -> list[str]:
        with self._lock:
            rows = self._connection.execute("SELECT DISTINCT asset_id FROM telemetry ORDER BY asset_id").fetchall()
        return [str(row["asset_id"]) for row in rows]

    def upsert_alarm(self, alarm: dict[str, Any]) -> None:
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT active, raised_at FROM alarms WHERE alarm_key=?", (alarm["alarm_key"],)
            ).fetchone()
            active = 1 if alarm.get("active", True) else 0
            raised_at = (existing["raised_at"] if existing and active else None) or alarm.get("raised_at") or utc_now()
            cleared_at = alarm.get("cleared_at")
            payload = dict(alarm)
            payload["raised_at"] = raised_at
            self._connection.execute(
                """
                INSERT INTO alarms(alarm_key, asset_id, code, severity, active, raised_at, cleared_at, message, payload_json)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(alarm_key) DO UPDATE SET
                  active=excluded.active,
                  severity=excluded.severity,
                  cleared_at=excluded.cleared_at,
                  message=excluded.message,
                  payload_json=excluded.payload_json
                """,
                (
                    alarm["alarm_key"], alarm["asset_id"], alarm["code"], alarm["severity"], active,
                    raised_at, cleared_at, alarm["message"], json.dumps(payload, ensure_ascii=False),
                ),
            )
            if existing is None:
                self._records["alarms"] = self._records.get("alarms", 0) + 1
            if existing is None or int(existing["active"]) != active:
                self._connection.execute(
                    "INSERT INTO alarm_history(timestamp, alarm_key, asset_id, code, severity, action, payload_json) VALUES(?,?,?,?,?,?,?)",
                    (
                        utc_now(), alarm["alarm_key"], alarm["asset_id"], alarm["code"], alarm["severity"],
                        "raised" if active else "cleared", json.dumps(payload, ensure_ascii=False),
                    ),
                )
                self._records["alarm_history"] = self._records.get("alarm_history", 0) + 1

    def list_alarms(self, *, active_only: bool = True, limit: int = 500) -> list[dict[str, Any]]:
        sql = "SELECT payload_json FROM alarms"
        args: list[Any] = []
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY raised_at DESC LIMIT ?"
        args.append(max(1, min(limit, 5000)))
        with self._lock:
            rows = self._connection.execute(sql, args).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def list_alarm_history(self, *, limit: int = 500, since: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM alarm_history"
        args: list[Any] = []
        if since:
            sql += " WHERE timestamp>=?"
            args.append(since)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(max(1, min(limit, 5000)))
        with self._lock:
            rows = self._connection.execute(sql, args).fetchall()
        return [
            {
                "timestamp": row["timestamp"], "alarm_key": row["alarm_key"], "asset_id": row["asset_id"],
                "code": row["code"], "severity": row["severity"], "action": row["action"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def audit_command(
        self,
        username: str,
        asset_id: str,
        point_key: str,
        requested_value: Any,
        status: str,
        response: dict[str, Any],
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO command_audit(timestamp,username,asset_id,point_key,requested_value_json,status,response_json) VALUES(?,?,?,?,?,?,?)",
                (
                    utc_now(), username, asset_id, point_key, json.dumps(requested_value, ensure_ascii=False), status,
                    json.dumps(response, ensure_ascii=False),
                ),
            )
            self._records["command_audit"] = self._records.get("command_audit", 0) + 1

    def list_command_audit(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM command_audit ORDER BY id DESC LIMIT ?", (max(1, min(limit, 5000)),)
            ).fetchall()
        return [
            {
                "timestamp": row["timestamp"], "username": row["username"], "asset_id": row["asset_id"],
                "point_key": row["point_key"], "requested_value": json.loads(row["requested_value_json"]),
                "status": row["status"], "response": json.loads(row["response_json"]),
            }
            for row in rows
        ]

    def event(self, event_type: str, message: str, *, asset_id: str | None = None, payload: dict[str, Any] | None = None) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO events(timestamp,event_type,asset_id,message,payload_json) VALUES(?,?,?,?,?)",
                (utc_now(), event_type, asset_id, message, json.dumps(payload or {}, ensure_ascii=False)),
            )
            self._records["events"] = self._records.get("events", 0) + 1

    def list_events(self, *, limit: int = 500, since: str | None = None, event_type: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        args: list[Any] = []
        if since:
            clauses.append("timestamp>=?")
            args.append(since)
        if event_type:
            clauses.append("event_type=?")
            args.append(event_type)
        sql = "SELECT * FROM events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(max(1, min(limit, 5000)))
        with self._lock:
            rows = self._connection.execute(sql, args).fetchall()
        return [
            {
                "timestamp": row["timestamp"], "event_type": row["event_type"], "asset_id": row["asset_id"],
                "message": row["message"], "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    @staticmethod
    def to_csv(rows: list[dict[str, Any]]) -> str:
        output = io.StringIO()
        if not rows:
            output.write("no_data\n")
            return output.getvalue()
        fieldnames: list[str] = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = {
                key: json.dumps(value, ensure_ascii=False, separators=(",", ":")) if isinstance(value, (dict, list)) else value
                for key, value in row.items()
            }
            writer.writerow(flat)
        return output.getvalue()

    def read_log_tail(self, *, lines: int = 300) -> list[str]:
        if not self.log_path.exists():
            return []
        requested = max(1, min(lines, 5000))
        with self.log_path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.readlines()[-requested:]

    def _file_bytes(self) -> int:
        total = 0
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(self.database_path) + suffix)
            if candidate.exists():
                total += candidate.stat().st_size
        if self.log_path.exists():
            total += self.log_path.stat().st_size
        return total

    def telemetry_size_stats(self) -> dict[str, float | int]:
        with self._lock:
            return dict(self._telemetry_size)

    def status(self) -> dict[str, Any]:
        try:
            usage = os.statvfs(self.root)
            free_bytes = usage.f_bavail * usage.f_frsize
            total_bytes = usage.f_blocks * usage.f_frsize
        except OSError:
            free_bytes = total_bytes = None
        with self._lock:
            counts = dict(self._records)
            telemetry_size = dict(self._telemetry_size)
        application_bytes = self._file_bytes()
        quota = self.quota_bytes
        return {
            "root": str(self.root),
            "database": str(self.database_path),
            "log_file": str(self.log_path),
            "storage_mode": "preferred_sd" if self.using_preferred_storage else "fallback_rootfs",
            "preferred_mount_point": self.config.preferred_mount_point,
            "preferred_mount_ready": self.preferred_mount_ready,
            "preferred_mount_required": self.config.require_preferred_mount,
            "is_preferred_sd_path": self.using_preferred_storage,
            "free_bytes": free_bytes,
            "filesystem_total_bytes": total_bytes,
            "database_bytes": self.database_path.stat().st_size if self.database_path.exists() else 0,
            "application_bytes": application_bytes,
            "quota_bytes": quota,
            "quota_used_percent": round((application_bytes / quota) * 100, 4) if quota else None,
            "quota_remaining_bytes": max(0, quota - application_bytes),
            "records": counts,
            "telemetry_size": telemetry_size,
            "compression_enabled": self.config.compress_history,
            "compression_level": self.config.compression_level,
            "compact_history": self.config.compact_history,
            "effective_sample_interval_seconds": self.sample_interval_seconds,
            "effective_retention_days": self.retention_days,
        }

    def _delete_oldest_telemetry_batch(self, count: int = 10000) -> int:
        with self._lock, self._connection:
            return self._connection.execute(
                "DELETE FROM telemetry WHERE id IN (SELECT id FROM telemetry ORDER BY id LIMIT ?)",
                (count,),
            ).rowcount

    def enforce_retention(self) -> dict[str, int]:
        telemetry_cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat()
        audit_cutoff = (datetime.now(timezone.utc) - timedelta(days=max(self.retention_days, 365))).isoformat()
        removed: dict[str, int] = {}
        with self._lock, self._connection:
            removed["telemetry_age"] = self._connection.execute(
                "DELETE FROM telemetry WHERE timestamp<?", (telemetry_cutoff,)
            ).rowcount
            removed["alarm_history"] = self._connection.execute(
                "DELETE FROM alarm_history WHERE timestamp<?", (audit_cutoff,)
            ).rowcount
            removed["events"] = self._connection.execute(
                "DELETE FROM events WHERE timestamp<?", (audit_cutoff,)
            ).rowcount
        high_watermark = self.quota_bytes * (self.config.quota_high_watermark_percent / 100.0)
        removed_quota = 0
        while self._file_bytes() > high_watermark:
            deleted = self._delete_oldest_telemetry_batch()
            removed_quota += deleted
            if deleted == 0:
                break
        removed["telemetry_quota"] = removed_quota
        with self._lock:
            self._connection.execute("PRAGMA wal_checkpoint(PASSIVE)")
        self._load_status_counters()
        return removed
