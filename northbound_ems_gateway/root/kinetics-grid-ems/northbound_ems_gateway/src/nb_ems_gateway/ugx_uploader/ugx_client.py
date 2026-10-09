from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from .config import UGXServerConfig

LOG = logging.getLogger(__name__)


class UGXTelemetryClient:
    def __init__(self, config: UGXServerConfig, *, dry_run: bool = True) -> None:
        self.config = config
        self.dry_run = dry_run

    def post_records(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        url = self.config.telemetry_url
        if not records:
            return {"ok": True, "skipped": True, "reason": "no_records"}
        payload_bytes = len(json.dumps(records, separators=(",", ":")).encode("utf-8"))
        if self.dry_run:
            LOG.info("DRY RUN UGX POST records=%s bytes=%s url=%s", len(records), payload_bytes, url)
            return {"ok": True, "dry_run": True, "records": len(records), "payload_bytes": payload_bytes, "url": url}
        headers = {"Content-Type": "application/json", **self.config.extra_headers}
        try:
            with httpx.Client(timeout=self.config.timeout_sec, verify=self.config.verify_tls) as client:
                response = client.post(url, json=records, headers=headers)
            ok = 200 <= response.status_code < 300
            result: dict[str, Any] = {
                "ok": ok,
                "status_code": response.status_code,
                "records": len(records),
                "payload_bytes": payload_bytes,
                "url": url,
            }
            text = response.text[:1000] if response.text else ""
            if text:
                result["response_text"] = text
            if not ok:
                LOG.warning("UGX POST failed status=%s body=%s", response.status_code, text)
            return result
        except Exception as exc:
            LOG.exception("UGX POST exception")
            return {"ok": False, "error": str(exc), "records": len(records), "payload_bytes": payload_bytes, "url": url}
