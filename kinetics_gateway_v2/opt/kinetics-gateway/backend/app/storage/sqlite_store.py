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
    if not config.require_preferred_mount:
        return True
    mount_point = Path(config.preferred_mount_point)
    return mount_point.exists() and os.path.ismount(mount_point)


def choose_storage_root(config: StorageConfig) -> Path:
    preferred = Path(config.preferred_root)
    fallback = Path(config.fallback_root)
    if not fallback.is_absolute():
        fallback = project_root() / fallback
    candidates: list[Path] = []
    if _is_mount_ready(config):
        candidates.append(preferred)
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
        self.root = choose_storage_root(config)
        self.database_path = self.root / config.database_name
        self.log_path = self.root / config.log_name
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    @property
    def quota_bytes(self) -> int:
        return int(self.config.quota_gb * 1024**3)

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

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _encode_payload(payload: dict[str, Any], compress: bool) -> tuple[str, bytes | None, str, int, int]:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if compress:
            blob = zlib.compress(raw, level=6)
            return "", blob, "zlib-json", len(raw), len(blob)
        text = raw.decode("utf-8")
        return text, None, "json", len(raw), len(raw)

    @staticmethod
    def _decode_payload(row: sqlite3.Row) -> dict[str, Any]:
        encoding = row["encoding"] if "encoding" in row.keys() else "json"
        if encoding == "zlib-json" and row["payload_blob"] is not None:
            return json.loads(zlib.decompress(row["payload_blob"]).decode("utf-8"))
        return json.loads(row["payload_json"] or "{}")

    def store_telemetry(self, asset_id: str, payload: dict[str, Any], timestamp: str | None = None) -> dict[str, int]:
        text, blob, encoding, raw_size, stored_size = self._encode_payload(
            payload, self.config.compress_history
        )
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO telemetry(
                    timestamp, asset_id, payload_json, payload_blob, encoding,
                    uncompressed_bytes, stored_bytes
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (timestamp or utc_now(), asset_id, text, blob, encoding, raw_size, stored_size),
            )
        return {"uncompressed_bytes": raw_size, "stored_bytes": stored_size}

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
            if existing is None or int(existing["active"]) != active:
                self._connection.execute(
                    "INSERT INTO alarm_history(timestamp, alarm_key, asset_id, code, severity, action, payload_json) VALUES(?,?,?,?,?,?,?)",
                    (
                        utc_now(), alarm["alarm_key"], alarm["asset_id"], alarm["code"], alarm["severity"],
                        "raised" if active else "cleared", json.dumps(payload, ensure_ascii=False),
                    ),
                )

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
            row = self._connection.execute(
                """
                SELECT COUNT(*) AS count,
                       COALESCE(SUM(uncompressed_bytes),0) AS raw_sum,
                       COALESCE(SUM(stored_bytes),0) AS stored_sum,
                       COALESCE(AVG(uncompressed_bytes),0) AS raw_avg,
                       COALESCE(AVG(stored_bytes),0) AS stored_avg
                FROM telemetry
                """
            ).fetchone()
        return {
            "records": int(row["count"]),
            "uncompressed_bytes_total": int(row["raw_sum"]),
            "stored_bytes_total": int(row["stored_sum"]),
            "average_uncompressed_bytes": float(row["raw_avg"]),
            "average_stored_bytes": float(row["stored_avg"]),
        }

    def status(self) -> dict[str, Any]:
        try:
            usage = os.statvfs(self.root)
            free_bytes = usage.f_bavail * usage.f_frsize
            total_bytes = usage.f_blocks * usage.f_frsize
        except OSError:
            free_bytes = total_bytes = None
        counts: dict[str, int] = {}
        with self._lock:
            for table in ("telemetry", "alarms", "alarm_history", "command_audit", "events"):
                counts[table] = int(self._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        application_bytes = self._file_bytes()
        quota = self.quota_bytes
        return {
            "root": str(self.root),
            "database": str(self.database_path),
            "log_file": str(self.log_path),
            "preferred_mount_point": self.config.preferred_mount_point,
            "preferred_mount_ready": Path(self.config.preferred_mount_point).exists() and os.path.ismount(self.config.preferred_mount_point),
            "preferred_mount_required": self.config.require_preferred_mount,
            "is_preferred_sd_path": str(self.root) == str(Path(self.config.preferred_root)),
            "free_bytes": free_bytes,
            "filesystem_total_bytes": total_bytes,
            "database_bytes": self.database_path.stat().st_size if self.database_path.exists() else 0,
            "application_bytes": application_bytes,
            "quota_bytes": quota,
            "quota_used_percent": round((application_bytes / quota) * 100, 4) if quota else None,
            "quota_remaining_bytes": max(0, quota - application_bytes),
            "records": counts,
            "telemetry_size": self.telemetry_size_stats(),
            "compression_enabled": self.config.compress_history,
            "compact_history": self.config.compact_history,
        }

    def _delete_oldest_telemetry_batch(self, count: int = 10000) -> int:
        with self._lock, self._connection:
            return self._connection.execute(
                "DELETE FROM telemetry WHERE id IN (SELECT id FROM telemetry ORDER BY id LIMIT ?)",
                (count,),
            ).rowcount

    def enforce_retention(self) -> dict[str, int]:
        telemetry_cutoff = (datetime.now(timezone.utc) - timedelta(days=self.config.telemetry_retention_days)).isoformat()
        audit_cutoff = (datetime.now(timezone.utc) - timedelta(days=max(self.config.telemetry_retention_days, 365))).isoformat()
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
        return removed
