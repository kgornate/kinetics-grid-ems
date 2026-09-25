from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

PriorityName = Literal["P0", "P1", "P2", "P3", "P4"]


class CentralIdentityConfig(BaseModel):
    site_id: str = "unityess-site-001"
    gateway_id: str = "unityess-gw-001"
    schema_version: str = "1.0"
    software_version: str = "central-sync-g2"


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


class LocalGatewayApiConfig(BaseModel):
    """Read-only local gateway API connection used by Central Sync producers.

    Credentials are intentionally resolved from environment variables so a
    plaintext password does not need to live in the JSON configuration.
    """

    base_url: str = "http://127.0.0.1:8000"
    login_path: str = "/api/auth/login"
    health_path: str = "/api/health"
    username: str = "internal"
    password: str | None = None
    password_env: str = "CENTRAL_SYNC_LOCAL_API_PASSWORD"
    token: str | None = None
    token_env: str = "CENTRAL_SYNC_LOCAL_API_TOKEN"
    verify_tls: bool = False
    timeout_sec: float = 5.0
    connect_timeout_sec: float = 2.0
    user_agent: str = "ornate-central-sync-local/1.0"

    @field_validator("login_path", "health_path")
    @classmethod
    def _normalize_path(cls, value: str) -> str:
        return value if value.startswith("/") else f"/{value}"

    @property
    def login_url(self) -> str:
        return self.base_url.rstrip("/") + self.login_path

    @property
    def health_url(self) -> str:
        return self.base_url.rstrip("/") + self.health_path

    def resolved_password(self) -> str | None:
        if self.password_env:
            value = os.getenv(self.password_env)
            if value:
                return value
        if self.password and self.password.startswith("ENV:"):
            return os.getenv(self.password[4:])
        return self.password

    def resolved_token(self) -> str | None:
        if self.token_env:
            value = os.getenv(self.token_env)
            if value:
                return value
        if self.token and self.token.startswith("ENV:"):
            return os.getenv(self.token[4:])
        return self.token


class GatewayHealthProducerConfig(BaseModel):
    enabled: bool = False
    stream: str = "gateway_health"
    substream: str = "gateway"
    poll_interval_sec: float = 5.0
    heartbeat_interval_sec: float = 30.0
    startup_emit: bool = True
    heartbeat_priority: PriorityName = "P3"
    transition_priority: PriorityName = "P1"
    status_file: str = "/var/lib/nb-ems-central-sync/gateway_health_producer_status.json"

    @field_validator("poll_interval_sec", "heartbeat_interval_sec")
    @classmethod
    def _positive_interval(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("producer intervals must be > 0")
        return float(value)


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
    local_gateway_api: LocalGatewayApiConfig = Field(default_factory=LocalGatewayApiConfig)
    gateway_health: GatewayHealthProducerConfig = Field(default_factory=GatewayHealthProducerConfig)
    outbox: OutboxConfig = Field(default_factory=OutboxConfig)
    uploader: UploaderConfig = Field(default_factory=UploaderConfig)
    status_file: str = "/var/lib/nb-ems-central-sync/status.json"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


def load_central_sync_config(path: str | Path) -> CentralSyncConfig:
    p = Path(path)
    with p.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return CentralSyncConfig.model_validate(raw)
