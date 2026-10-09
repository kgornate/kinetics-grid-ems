from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

PriorityName = Literal["P0", "P1", "P2", "P3", "P4"]


class CentralIdentityConfig(BaseModel):
    site_id: str = "kalpa"
    gateway_id: str = "kalpa-ems-gateway-001"
    organization_id: str = "ornate-solar"
    schema_version: str = "1.0"
    software_version: str = "kalpa-central-sync-v0.12"


class CentralBackendConfig(BaseModel):
    base_url: str = "https://central-backend.example.invalid"
    ingest_path: str = "/api/v1/ingest/batch"
    gateway_token: str | None = None
    gateway_token_env: str = "CENTRAL_SYNC_GATEWAY_TOKEN"
    verify_tls: bool = True
    timeout_sec: float = 15.0
    connect_timeout_sec: float = 5.0
    source_ip: str | None = None
    gzip_enabled: bool = True
    user_agent: str = "ornate-central-sync/0.12"

    @field_validator("ingest_path")
    @classmethod
    def _normalize_path(cls, value: str) -> str:
        return value if value.startswith("/") else f"/{value}"

    def resolved_token(self) -> str | None:
        if self.gateway_token_env:
            value = os.getenv(self.gateway_token_env)
            if value:
                return value
        if self.gateway_token and self.gateway_token.startswith("ENV:"):
            return os.getenv(self.gateway_token[4:])
        return self.gateway_token

    @property
    def ingest_url(self) -> str:
        return self.base_url.rstrip("/") + self.ingest_path


class LocalGatewayApiConfig(BaseModel):
    base_url: str = "http://127.0.0.1:8000"
    login_path: str = "/api/auth/login"
    health_path: str = "/api/health"
    telemetry_snapshot_path: str = "/api/telemetry/snapshot"
    normalized_snapshot_path: str = "/api/normalized/snapshot"
    alarms_history_path: str = "/api/alarms/history"
    commands_audit_path: str = "/api/commands/audit"
    control_status_all_path: str = "/api/control-sequence/status/all"
    control_status_compact_path: str = "/api/control-sequence/status/all/compact"
    platform_readiness_path: str = "/api/platform/readiness"
    username: str = "internal"
    password: str | None = None
    password_env: str = "CENTRAL_SYNC_LOCAL_API_PASSWORD"
    token: str | None = None
    token_env: str = "CENTRAL_SYNC_LOCAL_API_TOKEN"
    verify_tls: bool = False
    timeout_sec: float = 20.0
    connect_timeout_sec: float = 2.0
    user_agent: str = "ornate-central-sync-local/0.12"

    @field_validator(
        "login_path", "health_path", "telemetry_snapshot_path", "normalized_snapshot_path",
        "alarms_history_path", "commands_audit_path", "control_status_all_path",
        "control_status_compact_path", "platform_readiness_path",
    )
    @classmethod
    def _normalize_path(cls, value: str) -> str:
        return value if value.startswith("/") else f"/{value}"

    @property
    def login_url(self) -> str:
        return self.base_url.rstrip("/") + self.login_path

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


class SimpleProducerConfig(BaseModel):
    enabled: bool = False
    stream: str
    substream: str | None = None
    poll_interval_sec: float = 5.0
    heartbeat_interval_sec: float = 30.0
    priority: PriorityName = "P3"
    status_file: str = "/var/lib/ornate-central-sync/producer_status.json"

    @field_validator("poll_interval_sec", "heartbeat_interval_sec")
    @classmethod
    def _positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("producer timing values must be > 0")
        return float(value)


class FastBESSProducerConfig(SimpleProducerConfig):
    enabled: bool = True
    stream: str = "fast_bess_telemetry"
    substream: str = "bess_fast"
    poll_interval_sec: float = 1.0
    heartbeat_interval_sec: float = 1.0
    priority: PriorityName = "P1"
    status_file: str = "/var/lib/ornate-central-sync/s1_status.json"


class GeneralAssetProducerConfig(SimpleProducerConfig):
    enabled: bool = True
    stream: str = "general_asset_telemetry"
    substream: str | None = None
    poll_interval_sec: float = 1.0
    heartbeat_interval_sec: float = 30.0
    priority: PriorityName = "P3"
    status_file: str = "/var/lib/ornate-central-sync/s2_status.json"
    catalog_dir: str = "generated_protocols"


class GatewayHealthProducerConfig(SimpleProducerConfig):
    enabled: bool = True
    stream: str = "gateway_health"
    substream: str = "gateway"
    poll_interval_sec: float = 5.0
    heartbeat_interval_sec: float = 30.0
    priority: PriorityName = "P2"
    transition_priority: PriorityName = "P1"
    status_file: str = "/var/lib/ornate-central-sync/s3_status.json"


class AlarmEventProducerConfig(SimpleProducerConfig):
    enabled: bool = True
    stream: str = "alarms_events"
    substream: str = "events"
    poll_interval_sec: float = 1.0
    heartbeat_interval_sec: float = 60.0
    priority: PriorityName = "P1"
    state_file: str = "/var/lib/ornate-central-sync/s4_state.json"
    status_file: str = "/var/lib/ornate-central-sync/s4_status.json"
    startup_emit_existing: bool = False


class CompatibilityApplicationProducerConfig(SimpleProducerConfig):
    """S5/S6/S7 contract slots. Disabled unless that application is deployed."""
    source_path: str | None = None


class ConfigurationAuditProducerConfig(SimpleProducerConfig):
    enabled: bool = True
    stream: str = "configuration_audit"
    substream: str = "gateway"
    poll_interval_sec: float = 2.0
    heartbeat_interval_sec: float = 300.0
    priority: PriorityName = "P1"
    gateway_config_path: str = "configs/elecod_lineage_4pair_control_ready_template.json"
    central_sync_config_path: str = "configs/central_sync_frozen_v1_3_kalpa.json"
    state_file: str = "/var/lib/ornate-central-sync/s8_state.json"
    status_file: str = "/var/lib/ornate-central-sync/s8_status.json"


class ChargeDischargeProducerConfig(SimpleProducerConfig):
    enabled: bool = True
    stream: str = "battery_charge_discharge_control"
    substream: str = "pair_controller"
    poll_interval_sec: float = 1.0
    heartbeat_interval_sec: float = 5.0
    priority: PriorityName = "P1"
    status_file: str = "/var/lib/ornate-central-sync/s10_status.json"


class CommandDownlinkConfig(BaseModel):
    enabled: bool = False
    poll_path: str = "/api/v1/commands/pending"
    poll_interval_sec: float = 2.0
    max_commands_per_poll: int = 20
    ledger_path: str = "/var/lib/ornate-central-sync/command_ledger.db"
    status_file: str = "/var/lib/ornate-central-sync/d1_status.json"
    result_stream: str = "command_results"
    result_substream: str = "commands"
    result_priority: PriorityName = "P0"
    stage_confirmation_phrase: str = "EXECUTE_STAGE_WRITE"
    automatic_confirmation_phrase: str = "EXECUTE_AUTOMATIC_SEQUENCE"
    allowed_command_types: list[str] = Field(default_factory=lambda: [
        "pair_precheck", "pair_automatic_start", "pair_set_power", "pair_zero_power",
        "pair_safe_stop", "pair_abort", "safe_stop_all",
    ])

    @field_validator("poll_path")
    @classmethod
    def _normalize_poll_path(cls, value: str) -> str:
        return value if value.startswith("/") else f"/{value}"


class OutboxConfig(BaseModel):
    path: str = "/var/lib/ornate-central-sync/central_sync.db"
    required_mount_path: str | None = None
    fail_if_mount_missing: bool = False
    acked_retention_hours: int = 24
    dead_letter_retention_days: int = 30
    transport_attempt_retention_days: int = 3
    max_db_size_mb: int = 1024
    min_free_space_mb: int = 256
    cleanup_interval_sec: float = 3600.0


class OverflowArchiveConfig(BaseModel):
    enabled: bool = True
    archive_dir: str = "/mnt/ems-logs/ornate-ems-gateway/backlog_archives"
    check_interval_sec: float = 2.0
    high_watermark_mb: int = 64
    target_watermark_mb: int = 32
    spill_min_age_sec: float = 60.0
    min_archive_free_space_mb: int = 1024
    max_messages_per_cycle: int = 100
    max_bytes_per_cycle: int = 8 * 1024 * 1024
    max_chunks_per_check: int = 4
    status_file: str = "/var/lib/ornate-central-sync/overflow_archiver_status.json"


class BacklogReplayConfig(BaseModel):
    enabled: bool = False
    archive_dir: str = "/mnt/ems-logs/ornate-ems-gateway/backlog_archives"
    status_file: str = "/var/lib/ornate-central-sync/backlog_replay_status.json"
    scan_interval_sec: float = 5.0
    request_pause_sec: float = 5.0
    max_messages_per_request: int = 25
    max_request_bytes: int = 512 * 1024
    live_pause_sendable_count: int = 50
    live_pause_oldest_age_sec: float = 5.0
    min_available_memory_mb: int = 500
    max_load1: float = 2.0
    delete_drained_archives: bool = True


class OverflowRecoveryConfig(BaseModel):
    enabled: bool = True
    archive_dir: str = "/mnt/ems-logs/ornate-ems-gateway/backlog_archives"
    archive_glob: str = "central_sync_overflow_*.db"
    status_file: str = "/var/lib/ornate-central-sync/overflow_recovery_status.json"
    uploader_status_file: str = "/var/lib/ornate-central-sync/overflow_recovery_uploader_status.json"
    marker_suffix: str = ".replayed.json"
    scan_interval_sec: float = 5.0
    request_pause_sec: float = 10.0
    max_messages_per_request: int = 25
    max_request_bytes: int = 128 * 1024
    live_pause_sendable_count: int = 25
    live_pause_oldest_age_sec: float = 3.0
    min_available_memory_mb: int = 500
    max_load1: float = 2.0


class UploaderConfig(BaseModel):
    scan_interval_sec: float = 1.0
    coalescing_window_sec: float = 1.0
    max_messages_per_request: int = 100
    max_request_bytes: int = 2 * 1024 * 1024
    worker_count: int = 1
    fair_batching_enabled: bool = True
    priority_bias_sec: float = 2.0
    candidate_scan_limit: int = 512
    backoff_initial_sec: float = 5.0
    backoff_multiplier: float = 2.0
    backoff_max_sec: float = 300.0
    jitter_percent: float = 0.20
    max_retry_after_sec: float = 600.0
    status_interval_sec: float = 2.0
    idle_sleep_sec: float = 0.25
    pause_file: str = "/var/lib/ornate-central-sync/uploader.pause"
    pause_poll_sec: float = 1.0


class CentralSyncConfig(BaseModel):
    enabled: bool = False
    identity: CentralIdentityConfig = Field(default_factory=CentralIdentityConfig)
    backend: CentralBackendConfig = Field(default_factory=CentralBackendConfig)
    local_gateway_api: LocalGatewayApiConfig = Field(default_factory=LocalGatewayApiConfig)
    fast_bess: FastBESSProducerConfig = Field(default_factory=FastBESSProducerConfig)
    general_assets: GeneralAssetProducerConfig = Field(default_factory=GeneralAssetProducerConfig)
    gateway_health: GatewayHealthProducerConfig = Field(default_factory=GatewayHealthProducerConfig)
    alarms_events: AlarmEventProducerConfig = Field(default_factory=AlarmEventProducerConfig)
    soc_controller: CompatibilityApplicationProducerConfig = Field(default_factory=lambda: CompatibilityApplicationProducerConfig(stream="soc_controller", substream="controller", status_file="/var/lib/ornate-central-sync/s5_status.json"))
    solis: CompatibilityApplicationProducerConfig = Field(default_factory=lambda: CompatibilityApplicationProducerConfig(stream="solis", substream="solis", status_file="/var/lib/ornate-central-sync/s6_status.json"))
    edge_ai: CompatibilityApplicationProducerConfig = Field(default_factory=lambda: CompatibilityApplicationProducerConfig(stream="edge_ai", substream="per_bess", status_file="/var/lib/ornate-central-sync/s7_status.json"))
    configuration_audit: ConfigurationAuditProducerConfig = Field(default_factory=ConfigurationAuditProducerConfig)
    charge_discharge: ChargeDischargeProducerConfig = Field(default_factory=ChargeDischargeProducerConfig)
    command_downlink: CommandDownlinkConfig = Field(default_factory=CommandDownlinkConfig)
    outbox: OutboxConfig = Field(default_factory=OutboxConfig)
    overflow_archive: OverflowArchiveConfig = Field(default_factory=OverflowArchiveConfig)
    overflow_recovery: OverflowRecoveryConfig = Field(default_factory=OverflowRecoveryConfig)
    backlog_replay: BacklogReplayConfig = Field(default_factory=BacklogReplayConfig)
    uploader: UploaderConfig = Field(default_factory=UploaderConfig)
    status_file: str = "/var/lib/ornate-central-sync/status.json"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


def load_central_sync_config(path: str | Path) -> CentralSyncConfig:
    p = Path(path)
    with p.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return CentralSyncConfig.model_validate(raw)
