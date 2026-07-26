from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class EndpointConfig(BaseModel):
    port: int = 503
    unit_id: int
    read_function_fallback: bool = True


class RackEndpointConfig(EndpointConfig):
    rack_id: int


class BmsConfig(BaseModel):
    enabled: bool = True
    architecture: Literal["three_level"] = "three_level"
    host: str = "10.30.4.13"
    source_ip: str | None = None
    timeout_seconds: float = 2.0
    address_offset: int = 0
    connection_mode: Literal["shared_port", "separate_ports"] = "shared_port"
    bau: EndpointConfig = Field(default_factory=lambda: EndpointConfig(port=503, unit_id=1))
    racks: list[RackEndpointConfig] = Field(
        default_factory=lambda: [
            RackEndpointConfig(rack_id=1, port=503, unit_id=2),
            RackEndpointConfig(rack_id=2, port=503, unit_id=3),
            RackEndpointConfig(rack_id=3, port=503, unit_id=4),
            RackEndpointConfig(rack_id=4, port=503, unit_id=5),
        ]
    )
    power_environment: EndpointConfig = Field(default_factory=lambda: EndpointConfig(port=503, unit_id=127))
    max_registers_per_request: int = 120
    max_gap_registers: int = 2
    poll_fast_seconds: float = 1.0
    poll_normal_seconds: float = 5.0
    poll_slow_seconds: float = 60.0
    poll_bulk_seconds: float = 30.0
    include_bulk_in_live_snapshot: bool = True
    write_enabled: bool = False


class PcsConfig(BaseModel):
    enabled: bool = True
    host: str = "0.0.0.0"
    source_ip: str | None = None
    port: int = 502
    unit_id: int = 1
    timeout_seconds: float = 2.0
    address_offset: int = 0
    poll_seconds: float = 5.0
    write_enabled: bool = False
    overrides_file: str = "configs/pcs_overrides.json"
    max_registers_per_request: int = 120


class StorageConfig(BaseModel):
    preferred_root: str = "/mnt/ems-logs/kinetics-gateway"
    preferred_mount_point: str = "/mnt/ems-logs"
    require_preferred_mount: bool = False
    fallback_root: str = "data"
    database_name: str = "kinetics_gateway.db"
    log_name: str = "kinetics_gateway.log"
    telemetry_retention_days: int = 90
    sample_interval_seconds: float = 5.0
    quota_gb: float = 25.0
    quota_high_watermark_percent: float = 90.0
    compact_history: bool = True
    compress_history: bool = True
    store_raw_when_distinct: bool = True


class SecurityConfig(BaseModel):
    jwt_secret_env: str = "KINETICS_JWT_SECRET"
    jwt_algorithm: str = "HS256"
    token_expiry_minutes: int = 720
    allow_dev_default_credentials: bool = True


class MockConfig(BaseModel):
    scenario: str = "normal"
    seed: int = 93
    full_array_length: bool = True


class NetworkConfig(BaseModel):
    topology: Literal["shared_switch", "separate_interfaces"] = "shared_switch"
    field_interface: str = "eth1"
    pc_interface: str = "eth0"
    wifi_interface: str = "mlan0"
    bms_interface: str = "eth1"
    pcs_interface: str = "eth1"
    pc_api_cidr: str = "192.168.10.2/24"
    field_primary_cidr: str = "10.30.4.2/24"
    field_secondary_cidrs: list[str] = Field(default_factory=list)


class GatewayConfig(BaseModel):
    gateway_id: str = "kinetics_gateway_1"
    mode: Literal["mock", "hardware", "mixed", "read_only", "control_enabled"] = "mock"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    telemetry_interval_seconds: float = 1.0
    bms_catalog_file: str = "generated_protocols/bms_catalog.json"
    pcs_catalog_file: str = "generated_protocols/pcs_catalog.json"
    bms: BmsConfig = Field(default_factory=BmsConfig)
    pcs: PcsConfig = Field(default_factory=PcsConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    mock: MockConfig = Field(default_factory=MockConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)

    @model_validator(mode="after")
    def validate_write_mode(self) -> "GatewayConfig":
        if self.mode == "read_only":
            self.bms.write_enabled = False
            self.pcs.write_enabled = False
        return self

    @property
    def is_mock(self) -> bool:
        return self.mode in {"mock", "mixed"}

    @property
    def hardware_enabled(self) -> bool:
        return self.mode in {"hardware", "mixed", "read_only", "control_enabled"}


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_path(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else project_root() / candidate


def load_config(path: str | Path | None = None) -> GatewayConfig:
    configured = path or os.getenv("KINETICS_CONFIG", "configs/kinetics_mock.json")
    resolved = resolve_path(str(configured))
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return GatewayConfig.model_validate(payload)
