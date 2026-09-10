from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_BASE_DIR = "/var/lib/nb-ems-soc-solis-controller"
DEFAULT_STATUS_PATH = os.environ.get(
    "NB_EMS_CONTROLLER_STATUS_PATH",
    f"{DEFAULT_BASE_DIR}/operator_status.json",
)
DEFAULT_HISTORY_DB_PATH = os.environ.get(
    "NB_EMS_CONTROLLER_HISTORY_DB",
    f"{DEFAULT_BASE_DIR}/operator_history.db",
)


class ControllerMonitorStore:
    """Small cross-process store shared by the SOC controller and gateway API.

    The controller writes one atomic JSON status snapshot every cycle and appends only
    meaningful events to a dedicated SQLite DB. The gateway API opens the same files
    for operator/Flutter reads. SQLite WAL mode keeps the writer and API readers from
    blocking each other during normal operation.
    """

    def __init__(self, status_path: str | None = None, history_db_path: str | None = None):
        self.status_path = Path(status_path or os.environ.get("NB_EMS_CONTROLLER_STATUS_PATH", DEFAULT_STATUS_PATH))
        self.history_db_path = Path(history_db_path or os.environ.get("NB_EMS_CONTROLLER_HISTORY_DB", DEFAULT_HISTORY_DB_PATH))
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.history_db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS controller_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    device TEXT,
                    controller_state TEXT,
                    decision TEXT,
                    soc_x REAL,
                    soc_y REAL,
                    solis_state TEXT,
                    solis_power_w INTEGER,
                    target TEXT,
                    result TEXT,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_controller_events_time ON controller_events(timestamp_utc DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_controller_events_type ON controller_events(event_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_controller_events_device ON controller_events(device)"
            )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def write_status(self, status: dict[str, Any]) -> None:
        data = dict(status)
        data.setdefault("available", True)
        payload = json.dumps(data, indent=2, sort_keys=False)
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=self.status_path.name + ".", suffix=".tmp", dir=str(self.status_path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_name, self.status_path)
        finally:
            try:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
            except Exception:
                pass

    def read_status(self) -> dict[str, Any]:
        try:
            data = json.loads(self.status_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("operator status is not a JSON object")
            data.setdefault("available", True)
            data.setdefault("status_path", str(self.status_path))
            return data
        except FileNotFoundError:
            return {
                "available": False,
                "reason": "controller_status_not_created_yet",
                "status_path": str(self.status_path),
            }
        except Exception as exc:
            return {
                "available": False,
                "reason": "controller_status_read_failed",
                "error": str(exc),
                "status_path": str(self.status_path),
            }

    def append_event(
        self,
        *,
        event_type: str,
        message: str,
        severity: str = "info",
        device: str | None = None,
        controller_state: str | None = None,
        decision: str | None = None,
        soc_x: float | None = None,
        soc_y: float | None = None,
        solis_state: str | None = None,
        solis_power_w: int | None = None,
        target: str | None = None,
        result: str | None = None,
        payload: dict[str, Any] | None = None,
        timestamp_utc: str | None = None,
    ) -> int:
        ts = timestamp_utc or self._utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO controller_events(
                    timestamp_utc,severity,event_type,device,controller_state,decision,
                    soc_x,soc_y,solis_state,solis_power_w,target,result,message,payload_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    ts,
                    str(severity).lower(),
                    event_type,
                    device,
                    controller_state,
                    decision,
                    soc_x,
                    soc_y,
                    solis_state,
                    solis_power_w,
                    target,
                    result,
                    message,
                    json.dumps(payload or {}, separators=(",", ":"), default=str),
                ),
            )
            return int(cur.lastrowid)

    def query_events(
        self,
        *,
        event_type: str | None = None,
        severity: str | None = None,
        device: str | None = None,
        result: str | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        limit: int = 100,
        offset: int = 0,
        order: str = "desc",
    ) -> dict[str, Any]:
        where: list[str] = []
        args: list[Any] = []
        for column, value in [
            ("event_type", event_type),
            ("severity", severity.lower() if severity else None),
            ("device", device),
            ("result", result),
        ]:
            if value is not None:
                where.append(f"{column}=?")
                args.append(value)
        if from_time:
            where.append("timestamp_utc>=?")
            args.append(from_time)
        if to_time:
            where.append("timestamp_utc<=?")
            args.append(to_time)
        clause = " WHERE " + " AND ".join(where) if where else ""
        direction = "ASC" if str(order).lower() == "asc" else "DESC"
        limit = max(1, min(int(limit), 1000))
        offset = max(0, int(offset))
        with self._connect() as conn:
            total = int(conn.execute("SELECT COUNT(*) FROM controller_events" + clause, args).fetchone()[0])
            rows = conn.execute(
                f"SELECT * FROM controller_events{clause} ORDER BY timestamp_utc {direction}, id {direction} LIMIT ? OFFSET ?",
                args + [limit, offset],
            ).fetchall()
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "order": direction.lower(),
            "items": [self._event_row(row) for row in rows],
        }

    def cleanup(self, *, retention_days: int = 30, max_events: int = 20000) -> dict[str, Any]:
        retention_days = max(1, int(retention_days))
        max_events = max(100, int(max_events))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat(timespec="seconds")
        with self._connect() as conn:
            old_deleted = int(conn.execute("DELETE FROM controller_events WHERE timestamp_utc < ?", (cutoff,)).rowcount)
            count = int(conn.execute("SELECT COUNT(*) FROM controller_events").fetchone()[0])
            overflow_deleted = 0
            if count > max_events:
                overflow = count - max_events
                overflow_deleted = int(
                    conn.execute(
                        "DELETE FROM controller_events WHERE id IN (SELECT id FROM controller_events ORDER BY timestamp_utc ASC, id ASC LIMIT ?)",
                        (overflow,),
                    ).rowcount
                )
        return {
            "ok": True,
            "retention_days": retention_days,
            "max_events": max_events,
            "deleted_old": old_deleted,
            "deleted_overflow": overflow_deleted,
        }

    @staticmethod
    def _event_row(row: sqlite3.Row) -> dict[str, Any]:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except Exception:
            payload = {"raw": row["payload_json"]}
        return {
            "id": row["id"],
            "timestamp_utc": row["timestamp_utc"],
            "severity": row["severity"],
            "event_type": row["event_type"],
            "device": row["device"],
            "controller_state": row["controller_state"],
            "decision": row["decision"],
            "soc_x": row["soc_x"],
            "soc_y": row["soc_y"],
            "solis_state": row["solis_state"],
            "solis_power_w": row["solis_power_w"],
            "target": row["target"],
            "result": row["result"],
            "message": row["message"],
            "payload": payload,
        }
