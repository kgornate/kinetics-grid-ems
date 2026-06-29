from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SQLiteStore:
    """Small local historian for dashboard readiness and offline buffering.

    Version 1 stores read-only telemetry snapshots and event records. It does not
    store or execute commands.
    """

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telemetry_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telemetry_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    signal_name TEXT NOT NULL,
                    value REAL,
                    unit TEXT,
                    quality TEXT,
                    address INTEGER,
                    display_name TEXT,
                    category TEXT,
                    point_name TEXT
                )
                """
            )
            self.conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_telemetry_points_asset_signal_time
                ON telemetry_points(asset_id, signal_name, timestamp_utc)
                """
            )
            self.conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_telemetry_snapshots_asset_time
                ON telemetry_snapshots(asset_id, timestamp_utc)
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gateway_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT
                )
                """
            )
            self.conn.commit()

    def insert_asset_snapshot(self, asset_id: str, payload: dict[str, Any]) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        telemetry = payload.get("telemetry", {})
        with self._lock:
            self.conn.execute(
                "INSERT INTO telemetry_snapshots(timestamp_utc, asset_id, payload_json) VALUES (?, ?, ?)",
                (timestamp, asset_id, json.dumps(payload, ensure_ascii=False)),
            )
            rows = []
            for signal_name, entry in telemetry.items():
                rows.append(
                    (
                        timestamp,
                        asset_id,
                        signal_name,
                        entry.get("value"),
                        entry.get("unit"),
                        entry.get("quality"),
                        entry.get("address"),
                        entry.get("display_name"),
                        entry.get("category"),
                        entry.get("point_name"),
                    )
                )
            if rows:
                self.conn.executemany(
                    """
                    INSERT INTO telemetry_points(
                        timestamp_utc, asset_id, signal_name, value, unit, quality,
                        address, display_name, category, point_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
            self.conn.commit()

    def insert_snapshot(self, payload: dict[str, Any]) -> None:
        for asset_id, asset_payload in payload.items():
            if isinstance(asset_payload, dict):
                self.insert_asset_snapshot(asset_id, asset_payload)

    def insert_event(self, severity: str, event_type: str, message: str, payload: dict[str, Any] | None = None) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO gateway_events(timestamp_utc, severity, event_type, message, payload_json) VALUES (?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    severity,
                    event_type,
                    message,
                    json.dumps(payload or {}, ensure_ascii=False),
                ),
            )
            self.conn.commit()

    def latest_snapshots(self, *, limit: int = 50, asset_id: str | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        with self._lock:
            if asset_id:
                rows = self.conn.execute(
                    "SELECT id, timestamp_utc, asset_id, payload_json FROM telemetry_snapshots WHERE asset_id = ? ORDER BY id DESC LIMIT ?",
                    (asset_id, limit),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT id, timestamp_utc, asset_id, payload_json FROM telemetry_snapshots ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [
            {
                "id": row["id"],
                "timestamp_utc": row["timestamp_utc"],
                "asset_id": row["asset_id"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def latest_points(self, *, asset_id: str | None = None, signal_name: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 2000))
        query = "SELECT * FROM telemetry_points"
        args: list[Any] = []
        where: list[str] = []
        if asset_id:
            where.append("asset_id = ?")
            args.append(asset_id)
        if signal_name:
            where.append("signal_name = ?")
            args.append(signal_name)
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self.conn.execute(query, args).fetchall()
        return [dict(row) for row in rows]

    def status(self) -> dict[str, Any]:
        with self._lock:
            snap_count = self.conn.execute("SELECT COUNT(*) AS c FROM telemetry_snapshots").fetchone()["c"]
            point_count = self.conn.execute("SELECT COUNT(*) AS c FROM telemetry_points").fetchone()["c"]
            event_count = self.conn.execute("SELECT COUNT(*) AS c FROM gateway_events").fetchone()["c"]
        return {
            "enabled": True,
            "type": "sqlite",
            "path": str(self.path),
            "telemetry_snapshot_count": snap_count,
            "telemetry_point_count": point_count,
            "event_count": event_count,
        }

    def close(self) -> None:
        with self._lock:
            self.conn.close()
