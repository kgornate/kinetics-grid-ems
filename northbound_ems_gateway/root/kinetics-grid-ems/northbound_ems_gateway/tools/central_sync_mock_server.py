#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import sqlite3
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def build_app(state_db: str, reject_substream: str | None = None, reject_retryable: bool = True) -> FastAPI:
    app = FastAPI(title="Central Sync G1 Mock Backend")
    db_path = Path(state_db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS received(message_id TEXT PRIMARY KEY, received_count INTEGER NOT NULL DEFAULT 1, payload_json TEXT NOT NULL)")
    conn.commit()

    @app.post("/api/v1/ingest/batch")
    async def ingest(request: Request):
        raw = await request.body()
        if request.headers.get("content-encoding", "").lower() == "gzip":
            try:
                raw = gzip.decompress(raw)
            except Exception as exc:
                return JSONResponse(status_code=400, content={"detail": f"bad gzip: {exc}"})
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            return JSONResponse(status_code=400, content={"detail": f"bad json: {exc}"})
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        messages = body.get("messages") if isinstance(body, dict) else None
        if not isinstance(messages, list):
            return JSONResponse(status_code=400, content={"detail": "messages[] required"})
        for msg in messages:
            if not isinstance(msg, dict) or not msg.get("message_id"):
                continue
            mid = str(msg["message_id"])
            substream = str(msg.get("substream") or "")
            if reject_substream and substream == reject_substream:
                rejected.append({
                    "message_id": mid,
                    "error_code": "MOCK_REJECT",
                    "retryable": bool(reject_retryable),
                    "detail": "forced by G1 mock backend",
                })
                continue
            row = conn.execute("SELECT received_count FROM received WHERE message_id=?", (mid,)).fetchone()
            if row:
                conn.execute("UPDATE received SET received_count=received_count+1 WHERE message_id=?", (mid,))
                conn.commit()
                accepted.append({"message_id": mid, "status": "already_processed"})
            else:
                conn.execute("INSERT INTO received(message_id,payload_json) VALUES(?,?)", (mid, json.dumps(msg,separators=(",",":"))))
                conn.commit()
                accepted.append({"message_id": mid, "status": "accepted"})
        return {
            "request_id": body.get("request_id"),
            "gateway_id": body.get("gateway_id"),
            "accepted": accepted,
            "rejected": rejected,
        }

    @app.get("/api/mock/status")
    def status():
        rows = conn.execute("SELECT message_id,received_count FROM received ORDER BY rowid DESC LIMIT 100").fetchall()
        return {"unique_messages": conn.execute("SELECT COUNT(*) FROM received").fetchone()[0], "items": [dict(r) for r in rows]}

    @app.post("/api/mock/reset")
    def reset():
        conn.execute("DELETE FROM received"); conn.commit(); return {"ok": True}

    return app


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8081)
    p.add_argument("--state-db", default="/tmp/central_sync_mock.db")
    p.add_argument("--reject-substream")
    p.add_argument("--permanent-reject", action="store_true")
    args=p.parse_args()
    uvicorn.run(build_app(args.state_db,args.reject_substream,not args.permanent_reject), host=args.host, port=args.port, log_level="info")

if __name__ == "__main__":
    main()
