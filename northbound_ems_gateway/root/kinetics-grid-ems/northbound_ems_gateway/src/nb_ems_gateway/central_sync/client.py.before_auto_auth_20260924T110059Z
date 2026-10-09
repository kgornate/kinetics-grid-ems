from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from typing import Any

import httpx

from .config import CentralBackendConfig


@dataclass
class TransportResponse:
    status_code: int | None
    body: dict[str, Any] | None
    text: str
    retry_after_sec: float | None = None
    exception: str | None = None

    @property
    def ok(self) -> bool:
        return self.status_code is not None and 200 <= self.status_code < 300


class CentralBackendClient:
    def __init__(self, config: CentralBackendConfig, gateway_id: str) -> None:
        self.config = config
        self.gateway_id = gateway_id
        transport = httpx.AsyncHTTPTransport(
            local_address=config.source_ip,
            verify=config.verify_tls,
            retries=0,
        )
        timeout = httpx.Timeout(config.timeout_sec, connect=config.connect_timeout_sec)
        self.client = httpx.AsyncClient(
            transport=transport,
            timeout=timeout,
            headers={"User-Agent": config.user_agent},
        )

    async def post_batch(self, json_bytes: bytes) -> TransportResponse:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Gateway-ID": self.gateway_id,
        }
        token = self.config.resolved_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        content = json_bytes
        if self.config.gzip_enabled:
            content = gzip.compress(json_bytes)
            headers["Content-Encoding"] = "gzip"
        try:
            response = await self.client.post(self.config.ingest_url, content=content, headers=headers)
            retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
            text = response.text[:4000]
            body: dict[str, Any] | None = None
            try:
                parsed = response.json()
                if isinstance(parsed, dict):
                    body = parsed
            except Exception:
                body = None
            return TransportResponse(
                status_code=response.status_code,
                body=body,
                text=text,
                retry_after_sec=retry_after,
            )
        except Exception as exc:
            return TransportResponse(
                status_code=None,
                body=None,
                text="",
                exception=f"{type(exc).__name__}: {exc}",
            )

    async def close(self) -> None:
        await self.client.aclose()


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value.strip()))
    except Exception:
        return None
