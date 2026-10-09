from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class UploaderStateStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS uploader_state (key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_epoch_ms INTEGER NOT NULL)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS uploader_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp_epoch_ms INTEGER NOT NULL, profile TEXT, status TEXT, message TEXT, payload_json TEXT)"
        )
        self.conn.commit()

    def get(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute("SELECT value_json FROM uploader_state WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value_json"])
        except Exception:
            return default

    def set(self, key: str, value: Any) -> None:
        now_ms = int(time.time() * 1000)
        self.conn.execute(
            "INSERT INTO uploader_state(key,value_json,updated_epoch_ms) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_epoch_ms=excluded.updated_epoch_ms",
            (key, json.dumps(value, separators=(",", ":")), now_ms),
        )
        self.conn.commit()

    def get_int(self, key: str, default: int = 0) -> int:
        value = self.get(key, default)
        try:
            return int(value)
        except Exception:
            return default

    def set_int(self, key: str, value: int) -> None:
        self.set(key, int(value))

    def record_run(self, profile: str, status: str, message: str, payload: dict[str, Any] | None = None) -> None:
        now_ms = int(time.time() * 1000)
        self.conn.execute(
            "INSERT INTO uploader_runs(timestamp_epoch_ms,profile,status,message,payload_json) VALUES(?,?,?,?,?)",
            (now_ms, profile, status, message, json.dumps(payload or {}, separators=(",", ":"))),
        )
        self.conn.commit()

    def status(self) -> dict[str, Any]:
        states = {}
        for row in self.conn.execute("SELECT key,value_json,updated_epoch_ms FROM uploader_state ORDER BY key").fetchall():
            try:
                value = json.loads(row["value_json"])
            except Exception:
                value = row["value_json"]
            states[row["key"]] = {"value": value, "updated_epoch_ms": row["updated_epoch_ms"]}
        recent = []
        for row in self.conn.execute("SELECT * FROM uploader_runs ORDER BY id DESC LIMIT 20").fetchall():
            recent.append({
                "id": row["id"],
                "timestamp_epoch_ms": row["timestamp_epoch_ms"],
                "profile": row["profile"],
                "status": row["status"],
                "message": row["message"],
            })
        return {"path": str(self.path), "states": states, "recent_runs": recent}

    def close(self) -> None:
        self.conn.close()
