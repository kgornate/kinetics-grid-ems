from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from nb_ems_gateway.config.models import ServerUploadConfig
from .interface import get_ipv4_for_interface
from .payload import build_upload_payload

LOGGER = logging.getLogger(__name__)


@dataclass
class ServerUploadStatus:
    enabled: bool
    transport: str
    endpoint_url: str | None
    network_interface: str
    source_ip: str | None = None
    payload_mode: str = "key_signals"
    upload_interval_sec: float = 10.0
    queue_size: int = 0
    success_count: int = 0
    failure_count: int = 0
    dropped_count: int = 0
    last_attempt_utc: str | None = None
    last_success_utc: str | None = None
    last_error: str | None = None
    last_status_code: int | None = None
    last_response_text: str | None = None
    running: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "transport": self.transport,
            "endpoint_url": self.endpoint_url,
            "network_interface": self.network_interface,
            "source_ip": self.source_ip,
            "payload_mode": self.payload_mode,
            "upload_interval_sec": self.upload_interval_sec,
            "queue_size": self.queue_size,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "dropped_count": self.dropped_count,
            "last_attempt_utc": self.last_attempt_utc,
            "last_success_utc": self.last_success_utc,
            "last_error": self.last_error,
            "last_status_code": self.last_status_code,
            "last_response_text": self.last_response_text,
            "running": self.running,
        }


class ServerUploadService:
    """Background HTTPS REST uploader.

    This service is intentionally independent from the read-only Modbus polling
    path. A failed server upload must never stop telemetry acquisition, local API,
    local dashboard, or local SQLite storage.
    """

    def __init__(self, config: ServerUploadConfig, container: Any) -> None:
        self.config = config
        self.container = container
        self._task: asyncio.Task | None = None
        self._running = False
        self._queue: list[dict[str, Any]] = []
        self.status = ServerUploadStatus(
            enabled=config.enabled,
            transport=config.transport,
            endpoint_url=config.endpoint_url,
            network_interface=config.network_interface,
            payload_mode=config.payload_mode,
            upload_interval_sec=config.upload_interval_sec,
        )

    async def start(self) -> None:
        if not self.config.enabled:
            LOGGER.info("Server upload disabled by config.")
            return
        if not self.config.endpoint_url:
            self.status.last_error = "server_upload.endpoint_url is not configured"
            LOGGER.warning("Server upload enabled but endpoint_url is missing; upload task not started.")
            return
        if self.config.transport != "https_rest":
            self.status.last_error = f"Unsupported server upload transport: {self.config.transport}"
            LOGGER.warning(self.status.last_error)
            return
        self.status.source_ip = self.config.source_ip or get_ipv4_for_interface(self.config.network_interface)
        self._running = True
        self.status.running = True
        self._task = asyncio.create_task(self._run_loop())
        LOGGER.info(
            "Server upload started endpoint=%s interface=%s source_ip=%s interval=%ss",
            self.config.endpoint_url,
            self.config.network_interface,
            self.status.source_ip,
            self.config.upload_interval_sec,
        )

    async def stop(self) -> None:
        self._running = False
        self.status.running = False
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def upload_once(self) -> dict[str, Any]:
        if not self.config.enabled:
            return self.status.to_dict()
        payload = build_upload_payload(self.container, payload_mode=self.config.payload_mode)
        if self.config.buffer_when_offline:
            self._enqueue(payload)
            await self._flush_queue()
        else:
            await self._post_payload(payload)
        self.status.queue_size = len(self._queue)
        return self.status.to_dict()

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self.upload_once()
            except Exception as exc:
                self._mark_failure(error=f"Unexpected upload loop error: {exc}")
                LOGGER.warning("Unexpected server upload loop error: %s", exc)
            await asyncio.sleep(max(1.0, self.config.upload_interval_sec))

    def _enqueue(self, payload: dict[str, Any]) -> None:
        self._queue.append(payload)
        max_queue = max(1, self.config.max_queue_size)
        while len(self._queue) > max_queue:
            self._queue.pop(0)
            self.status.dropped_count += 1
        self.status.queue_size = len(self._queue)

    async def _flush_queue(self) -> None:
        # Send oldest first. Stop on first failure so pending data remains queued.
        while self._queue:
            payload = self._queue[0]
            ok = await self._post_payload(payload)
            if not ok:
                break
            self._queue.pop(0)
            self.status.queue_size = len(self._queue)

    async def _post_payload(self, payload: dict[str, Any]) -> bool:
        self.status.last_attempt_utc = datetime.now(timezone.utc).isoformat()
        self.status.last_error = None
        self.status.last_status_code = None
        self.status.last_response_text = None

        headers = {
            "Content-Type": "application/json",
            "X-Gateway-ID": self.container.config.gateway.id,
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        try:
            async with self._client() as client:
                response = await client.post(self.config.endpoint_url, json=payload, headers=headers)
            self.status.last_status_code = response.status_code
            self.status.last_response_text = response.text[:500] if response.text else ""
            if 200 <= response.status_code < 300:
                self.status.success_count += 1
                self.status.last_success_utc = datetime.now(timezone.utc).isoformat()
                if self.container.storage:
                    self.container.storage.insert_event(
                        "info",
                        "server_upload_success",
                        f"Uploaded telemetry snapshot to server, status={response.status_code}",
                        {"endpoint_url": self._safe_endpoint(), "interface": self.config.network_interface},
                    )
                return True
            self._mark_failure(error=f"HTTP {response.status_code}: {response.text[:200]}", status_code=response.status_code)
            return False
        except Exception as exc:
            self._mark_failure(error=str(exc))
            return False

    def _client(self) -> httpx.AsyncClient:
        local_address = self.status.source_ip if self.config.bind_to_interface_source_ip else None
        transport = httpx.AsyncHTTPTransport(local_address=local_address, retries=0, verify=self.config.verify_tls)
        return httpx.AsyncClient(transport=transport, timeout=self.config.timeout_sec)

    def _mark_failure(self, *, error: str, status_code: int | None = None) -> None:
        self.status.failure_count += 1
        self.status.last_error = error
        self.status.last_status_code = status_code
        LOGGER.warning("Server upload failed: %s", error)
        if self.container.storage:
            self.container.storage.insert_event(
                "warning",
                "server_upload_failed",
                error,
                {"endpoint_url": self._safe_endpoint(), "interface": self.config.network_interface},
            )

    def _safe_endpoint(self) -> str | None:
        if not self.config.endpoint_url:
            return None
        parsed = urlparse(self.config.endpoint_url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
