from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI(title="Example NorthBound EMS Backend Receiver")
DATA_DIR = Path(os.getenv("BACKEND_DATA_DIR", "received_payloads"))
API_TOKEN = os.getenv("BACKEND_API_TOKEN", "CHANGE_ME_API_TOKEN")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "example_backend_receiver"}


@app.post("/api/v1/gateway/telemetry")
async def receive_gateway_telemetry(
    request: Request,
    authorization: str | None = Header(default=None),
    x_gateway_id: str | None = Header(default=None),
) -> dict[str, Any]:
    expected = f"Bearer {API_TOKEN}"
    if API_TOKEN and authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid bearer token")

    payload = await request.json()
    gateway_id = x_gateway_id or payload.get("gateway", {}).get("id") or "unknown_gateway"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_file = DATA_DIR / f"{gateway_id}_{timestamp}.json"
    output_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    return {
        "accepted": True,
        "gateway_id": gateway_id,
        "stored_file": str(output_file),
        "schema_version": payload.get("schema_version"),
        "asset_count": len(payload.get("assets", {})),
    }
