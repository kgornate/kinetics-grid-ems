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
    controller_status_path: str = "/api/controller/status"
    controller_history_path: str = "/api/controller/history"
    solis_status_path: str = "/api/solis/status"
    solis_history_path: str = "/api/solis/history"
    username: str = "internal"
    password: str | None = None
    password_env: str = "CENTRAL_SYNC_LOCAL_API_PASSWORD"
    token: str | None = None
    token_env: str = "CENTRAL_SYNC_LOCAL_API_TOKEN"
    verify_tls: bool = False
    timeout_sec: float = 20.0
    connect_timeout_sec: float = 2.0
    user_agent: str = "ornate-central-sync-local/1.0"

    @field_validator("login_path", "health_path", "controller_status_path", "controller_history_path", "solis_status_path", "solis_history_path")
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


class FastBESSProducerConfig(BaseModel):
    enabled: bool = False
    stream: str = "fast_bess_telemetry"
    substream: str = "critical_pcs_bms"
    sample_interval_sec: float = 1.0
    priority: PriorityName = "P2"
    live_snapshot_path: str = "/run/nb-ems/fast_bess_live.json"
    max_snapshot_age_sec: float = 5.0
    expected_sources: list[str] = Field(default_factory=lambda: ["external_ems_1", "external_ems_2"])
    expected_bess_count: int = 2
    expected_pcs_signal_count: int = 28
    expected_bms_signal_count: int = 35
    strict_shape: bool = True
    status_file: str = "/var/lib/nb-ems-central-sync/fast_bess_producer_status.json"

    @field_validator("sample_interval_sec", "max_snapshot_age_sec")
    @classmethod
    def _positive_fast_bess_interval(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("fast BESS timing values must be > 0")
        return float(value)

    @field_validator("expected_bess_count", "expected_pcs_signal_count", "expected_bms_signal_count")
    @classmethod
    def _nonnegative_expected_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("expected Fast BESS counts must be >= 0")
        return int(value)


class GeneralAssetProducerConfig(BaseModel):
    enabled: bool = False
    stream: str = "general_asset_telemetry"
    poll_interval_sec: float = 1.0
    priority: PriorityName = "P3"
    live_snapshot_path: str = "/run/nb-ems/general_asset_live.json"
    policy_manifest_path: str = "data/central_sync/canonical_signal_policy_frozen_v1_1.json"
    max_snapshot_age_sec: float = 5.0
    expected_sources: list[str] = Field(default_factory=lambda: ["external_ems_1", "external_ems_2"])
    expected_source_count: int = 2
    expected_asset_record_count: int = 18
    expected_s2_canonical_count: int = 1350
    expected_s2_runtime_count: int = 2700
    strict_shape: bool = True
    status_file: str = "/var/lib/nb-ems-central-sync/general_asset_producer_status.json"

    @field_validator("poll_interval_sec", "max_snapshot_age_sec")
    @classmethod
    def _positive_general_asset_timing(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("general asset timing values must be > 0")
        return float(value)

    @field_validator(
        "expected_source_count",
        "expected_asset_record_count",
        "expected_s2_canonical_count",
        "expected_s2_runtime_count",
    )
    @classmethod
    def _nonnegative_general_asset_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("general asset expected counts must be >= 0")
        return int(value)


class SocControllerProducerConfig(BaseModel):
    enabled: bool = False
    stream: str = "soc_controller"
    substream: str = "controller"
    poll_interval_sec: float = 1.0
    heartbeat_interval_sec: float = 30.0
    startup_emit: bool = True
    heartbeat_priority: PriorityName = "P1"
    transition_priority: PriorityName = "P1"
    event_priority: PriorityName = "P1"
    history_poll_limit: int = 1000
    state_file: str = "/var/lib/nb-ems-central-sync/s5_soc_controller_state.json"
    status_file: str = "/var/lib/nb-ems-central-sync/s5_soc_controller_producer_status.json"

    @field_validator("poll_interval_sec", "heartbeat_interval_sec")
    @classmethod
    def _positive_s5_timing(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("S5 timing values must be > 0")
        return float(value)

    @field_validator("history_poll_limit")
    @classmethod
    def _positive_s5_history_limit(cls, value: int) -> int:
        if value < 1 or value > 1000:
            raise ValueError("S5 history_poll_limit must be between 1 and 1000")
        return int(value)


class SolisProducerConfig(BaseModel):
    enabled: bool = False
    stream: str = "solis"
    substream: str | None = None
    poll_interval_sec: float = 1.0
    heartbeat_interval_sec: float = 5.0
    history_poll_interval_sec: float = 5.0
    stale_after_sec: float = 15.0
    startup_emit: bool = True
    heartbeat_priority: PriorityName = "P1"
    transition_priority: PriorityName = "P1"
    event_priority: PriorityName = "P1"
    history_poll_limit: int = 1000
    state_file: str = "/var/lib/nb-ems-central-sync/s6_solis_state.json"
    status_file: str = "/var/lib/nb-ems-central-sync/s6_solis_producer_status.json"

    @field_validator(
        "poll_interval_sec",
        "heartbeat_interval_sec",
        "history_poll_interval_sec",
        "stale_after_sec",
    )
    @classmethod
    def _positive_s6_timing(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("S6 timing values must be > 0")
        return float(value)

    @field_validator("history_poll_limit")
    @classmethod
    def _positive_s6_history_limit(cls, value: int) -> int:
        if value < 1 or value > 1000:
            raise ValueError("S6 history_poll_limit must be between 1 and 1000")
        return int(value)


class EdgeAIProducerConfig(BaseModel):
    enabled: bool = False
    stream: str = "edge_ai"
    substream: str = "anomaly_detection"
    poll_interval_sec: float = 1.0
    stale_after_sec: float = 90.0
    status_heartbeat_interval_sec: float = 60.0
    inference_priority: PriorityName = "P2"
    anomaly_priority: PriorityName = "P1"
    status_transition_priority: PriorityName = "P1"
    status_heartbeat_priority: PriorityName = "P3"
    expected_feature_count: int = 33
    latest_json_path: str = "/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/live_inference_v0_3/latest_ml_health_v0_3.json"
    model_manifest_path: str = "/root/kinetics-grid-ems/northbound_ems_gateway/edge_ai_poc/runtime_v0_3/phase7_runtime_bundle_v0_3/model/ml_model_manifest_v0_3.json"
    state_file: str = "/var/lib/nb-ems-central-sync/s7_edge_ai_state.json"
    status_file: str = "/var/lib/nb-ems-central-sync/s7_edge_ai_producer_status.json"

    @field_validator("poll_interval_sec", "stale_after_sec", "status_heartbeat_interval_sec")
    @classmethod
    def _positive_s7_timing(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("S7 timing values must be > 0")
        return float(value)

    @field_validator("expected_feature_count")
    @classmethod
    def _positive_s7_feature_count(cls, value: int) -> int:
        if value < 1:
            raise ValueError("S7 expected_feature_count must be >= 1")
        return int(value)


class AlarmEventProducerConfig(BaseModel):
    enabled: bool = False
    stream: str = "alarms_events"
    poll_interval_sec: float = 1.0
    general_snapshot_path: str = "/run/nb-ems/general_asset_live.json"
    fast_bess_snapshot_path: str = "/run/nb-ems/fast_bess_live.json"
    trigger_manifest_path: str = "data/central_sync/s4_event_trigger_catalog_frozen_v1_1.json"
    max_snapshot_age_sec: float = 5.0
    expected_sources: list[str] = Field(default_factory=lambda: ["external_ems_1", "external_ems_2"])
    expected_canonical_trigger_count: int = 342
    expected_runtime_trigger_count: int = 684
    strict_shape: bool = True
    startup_emit_active: bool = True
    critical_priority: PriorityName = "P0"
    high_priority: PriorityName = "P1"
    warning_priority: PriorityName = "P2"
    info_priority: PriorityName = "P3"
    state_file: str = "/var/lib/nb-ems-central-sync/s4_event_state.json"
    status_file: str = "/var/lib/nb-ems-central-sync/s4_alarm_event_producer_status.json"

    @field_validator("poll_interval_sec", "max_snapshot_age_sec")
    @classmethod
    def _positive_s4_timing(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("S4 timing values must be > 0")
        return float(value)

    @field_validator("expected_canonical_trigger_count", "expected_runtime_trigger_count")
    @classmethod
    def _nonnegative_s4_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("S4 expected counts must be >= 0")
        return int(value)


class OutboxConfig(BaseModel):
    path: str = "/var/lib/nb-ems-central-sync/central_sync.db"
    required_mount_path: str | None = None
    fail_if_mount_missing: bool = True
    acked_retention_hours: int = 24
    dead_letter_retention_days: int = 30
    transport_attempt_retention_days: int = 3
    max_db_size_mb: int = 1024
    min_free_space_mb: int = 256
    cleanup_interval_sec: float = 3600.0


class OverflowArchiveConfig(BaseModel):
    """Keep the live outbox small by moving old unsent rows to archive DBs."""

    enabled: bool = True
    archive_dir: str = "/mnt/ems-logs/northbound_ems_gateway/backlog_archives"
    check_interval_sec: float = 2.0
    high_watermark_mb: int = 64
    target_watermark_mb: int = 32
    spill_min_age_sec: float = 60.0
    min_archive_free_space_mb: int = 4096
    max_messages_per_cycle: int = 100
    max_bytes_per_cycle: int = 8 * 1024 * 1024
    max_chunks_per_check: int = 4
    status_file: str = "/var/lib/nb-ems-central-sync/overflow_archiver_status.json"

    @field_validator("check_interval_sec", "spill_min_age_sec")
    @classmethod
    def _positive_overflow_timing(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("overflow archive timing values must be > 0")
        return float(value)

    @field_validator("high_watermark_mb", "target_watermark_mb", "min_archive_free_space_mb", "max_messages_per_cycle", "max_bytes_per_cycle", "max_chunks_per_check")
    @classmethod
    def _positive_overflow_limits(cls, value: int) -> int:
        if value < 1:
            raise ValueError("overflow archive limits must be >= 1")
        return int(value)


class BacklogReplayConfig(BaseModel):
    """Low-priority historical replay policy. Runs in a separate process."""

    enabled: bool = False
    archive_dir: str = "/mnt/ems-logs/northbound_ems_gateway/backlog_archives"
    status_file: str = "/var/lib/nb-ems-central-sync/backlog_replay_status.json"
    scan_interval_sec: float = 5.0
    request_pause_sec: float = 5.0
    max_messages_per_request: int = 25
    max_request_bytes: int = 512 * 1024
    live_pause_sendable_count: int = 50
    live_pause_oldest_age_sec: float = 5.0
    min_available_memory_mb: int = 700
    max_load1: float = 1.5
    delete_drained_archives: bool = True

    @field_validator("scan_interval_sec", "request_pause_sec", "live_pause_oldest_age_sec", "max_load1")
    @classmethod
    def _positive_replay_timing(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("backlog replay timing/load values must be > 0")
        return float(value)

    @field_validator("max_messages_per_request", "max_request_bytes", "min_available_memory_mb")
    @classmethod
    def _positive_replay_limits(cls, value: int) -> int:
        if value < 1:
            raise ValueError("backlog replay limits must be >= 1")
        return int(value)

    @field_validator("live_pause_sendable_count")
    @classmethod
    def _nonnegative_live_pause_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("live_pause_sendable_count must be >= 0")
        return int(value)


class UploaderConfig(BaseModel):
    scan_interval_sec: float = 1.0
    coalescing_window_sec: float = 1.0
    max_messages_per_request: int = 100
    max_request_bytes: int = 2 * 1024 * 1024
    worker_count: int = 1
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

    @field_validator("worker_count")
    @classmethod
    def _worker_count_bounded(cls, value: int) -> int:
        if value < 1 or value > 16:
            raise ValueError("worker_count must be between 1 and 16")
        return int(value)


class CentralSyncConfig(BaseModel):
    enabled: bool = False
    identity: CentralIdentityConfig = Field(default_factory=CentralIdentityConfig)
    backend: CentralBackendConfig = Field(default_factory=CentralBackendConfig)
    local_gateway_api: LocalGatewayApiConfig = Field(default_factory=LocalGatewayApiConfig)
    gateway_health: GatewayHealthProducerConfig = Field(default_factory=GatewayHealthProducerConfig)
    fast_bess: FastBESSProducerConfig = Field(default_factory=FastBESSProducerConfig)
    general_assets: GeneralAssetProducerConfig = Field(default_factory=GeneralAssetProducerConfig)
    alarms_events: AlarmEventProducerConfig = Field(default_factory=AlarmEventProducerConfig)
    soc_controller: SocControllerProducerConfig = Field(default_factory=SocControllerProducerConfig)
    solis: SolisProducerConfig = Field(default_factory=SolisProducerConfig)
    edge_ai: EdgeAIProducerConfig = Field(default_factory=EdgeAIProducerConfig)
    outbox: OutboxConfig = Field(default_factory=OutboxConfig)
    overflow_archive: OverflowArchiveConfig = Field(default_factory=OverflowArchiveConfig)
    backlog_replay: BacklogReplayConfig = Field(default_factory=BacklogReplayConfig)
    uploader: UploaderConfig = Field(default_factory=UploaderConfig)
    status_file: str = "/var/lib/nb-ems-central-sync/status.json"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


def load_central_sync_config(path: str | Path) -> CentralSyncConfig:
    p = Path(path)
    with p.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return CentralSyncConfig.model_validate(raw)
