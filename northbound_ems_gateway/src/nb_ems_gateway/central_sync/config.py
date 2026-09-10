from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CentralIdentityConfig(BaseModel):
    site_id: str = "unityess-site-001"
    gateway_id: str = "unityess-gw-001"
    schema_version: str = "1.0"
    software_version: str = "central-sync-g1"


class CentralBackendConfig(BaseModel):
    base_url: str = "http://192.168.10.1:8081"
    ingest_path: str = "/api/v1/ingest/batch"
    gateway_token: str | None = None
    gateway_token_env: str = "CENTRAL_SYNC_GATEWAY_TOKEN"
    verify_tls: bool = True
    timeout_sec: float = 15.0
    connect_timeout_sec: float = 5.0
    source_ip: str | None = None
    gzip_enabled: bool = True
    user_agent: str = "ornate-central-sync/1.0"

    @field_validator("ingest_path")
    @classmethod
    def _normalize_ingest_path(cls, value: str) -> str:
        return value if value.startswith("/") else f"/{value}"

    def resolved_token(self) -> str | None:
        if self.gateway_token_env:
            env_value = os.getenv(self.gateway_token_env)
            if env_value:
                return env_value
        if self.gateway_token and self.gateway_token.startswith("ENV:"):
            return os.getenv(self.gateway_token[4:])
        return self.gateway_token

    @property
    def ingest_url(self) -> str:
        return self.base_url.rstrip("/") + self.ingest_path


class OutboxConfig(BaseModel):
    path: str = "/var/lib/nb-ems-central-sync/central_sync.db"
    required_mount_path: str | None = None
    fail_if_mount_missing: bool = True
    acked_retention_hours: int = 24
    dead_letter_retention_days: int = 30
    max_db_size_mb: int = 1024
    min_free_space_mb: int = 256
    cleanup_interval_sec: float = 3600.0


class UploaderConfig(BaseModel):
    scan_interval_sec: float = 1.0
    coalescing_window_sec: float = 1.0
    max_messages_per_request: int = 100
    max_request_bytes: int = 2 * 1024 * 1024
    backoff_initial_sec: float = 5.0
    backoff_multiplier: float = 2.0
    backoff_max_sec: float = 300.0
    jitter_percent: float = 0.20
    max_retry_after_sec: float = 600.0
    status_interval_sec: float = 2.0
    idle_sleep_sec: float = 0.25

    @field_validator("max_messages_per_request")
    @classmethod
    def _max_messages_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_messages_per_request must be >= 1")
        return value


class CentralSyncConfig(BaseModel):
    enabled: bool = False
    identity: CentralIdentityConfig = Field(default_factory=CentralIdentityConfig)
    backend: CentralBackendConfig = Field(default_factory=CentralBackendConfig)
    outbox: OutboxConfig = Field(default_factory=OutboxConfig)
    uploader: UploaderConfig = Field(default_factory=UploaderConfig)
    status_file: str = "/var/lib/nb-ems-central-sync/status.json"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


def load_central_sync_config(path: str | Path) -> CentralSyncConfig:
    p = Path(path)
    with p.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return CentralSyncConfig.model_validate(raw)
