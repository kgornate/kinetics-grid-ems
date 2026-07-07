from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

class AuthUserConfig(BaseModel):
    username: str
    display_name: str = ""
    role: Literal["customer_admin","internal_admin"]
    password_hash: str | None = None
    password_hash_env: str | None = None
    enabled: bool = True

class AuthConfig(BaseModel):
    enabled: bool = False
    token_expiry_minutes: int = 480
    jwt_secret: str | None = "northbound-dev-change-this-jwt-secret"
    jwt_secret_env: str = "NB_EMS_JWT_SECRET"
    users: list[AuthUserConfig] = Field(default_factory=list)

    @property
    def allowed_roles(self) -> set[str]:
        return {"customer_admin", "internal_admin"}

class GatewayConfig(BaseModel):
    id: str = "northbound_ems_gateway_1"
    name: str = "NorthBound EMS Gateway"
    mode: str = "read_only"

class NetworkConfig(BaseModel):
    field_interface: str = "eth1"
    application_interface: str = "eth0"

class ExistingEMSConfig(BaseModel):
    protocol: str = "modbus_tcp"
    host: str = "127.0.0.1"
    port: int = 502
    unit_id: int = 1
    register_function: str = "holding_registers"
    timeout_sec: float = 2.0
    retries: int = 2

class ExternalEMSUnitConfig(BaseModel):
    source_id: str
    display_name: str
    host: str
    port: int = 502
    unit_id: int = 1
    interface: str = "eth1"
    protocol: str = "modbus_tcp"
    register_function: str = "holding_registers"
    timeout_sec: float = 2.0
    retries: int = 2
    enabled: bool = True

class RegisterMapConfig(BaseModel):
    path: str = "data/register_maps/unity261pv_modbus_north_v1.json"

class DecodingConfig(BaseModel):
    data_type: str = "float32"
    registers_per_point: int = 2
    byte_order: Literal["ABCD","CDAB","BADC","DCBA"] = "ABCD"
    apply_factor: bool = True

class PollingConfig(BaseModel):
    enabled: bool = True
    default_interval_sec: float = 5.0
    fast_interval_sec: float = 1.0
    slow_interval_sec: float = 10.0
    max_registers_per_read: int = 120

class APIConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    commands_enabled: bool = False

class LogsAPIConfig(BaseModel):
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 7000

class StorageConfig(BaseModel):
    enabled: bool = True
    type: str = "sqlite"
    path: str = "/mnt/ems-logs/northbound_ems_gateway/nb_ems_gateway.db"
    required_mount_path: str | None = "/mnt/ems-logs"
    fail_if_mount_missing: bool = True
    min_free_space_mb: int = 512
    max_db_size_mb: int = 2048
    retention_days: int = 7
    store_mode: Literal["key_signals","full_snapshot"] = "key_signals"
    snapshot_interval_sec: float = 30.0
    cleanup_on_startup: bool = True
    vacuum_after_cleanup: bool = False

class ServerUploadConfig(BaseModel):
    enabled: bool = False
    transport: str = "https_rest"
    endpoint_url: str | None = None
    api_key: str | None = None
    network_interface: str = "mlan0"
    source_ip: str | None = None
    bind_to_interface_source_ip: bool = True
    upload_interval_sec: float = 10.0
    timeout_sec: float = 5.0
    payload_mode: str = "key_signals"
    buffer_when_offline: bool = True
    max_queue_size: int = 1000
    verify_tls: bool = True

class LoggingConfig(BaseModel):
    enabled: bool = True
    min_severity: str = "debug"
    store_access_logs: bool = True
    store_poll_events: bool = True
    store_server_upload_events: bool = True
    store_telemetry_quality_events: bool = True
    max_query_limit: int = 1000
    default_query_limit: int = 200
    retention_days: int = 30
    export_max_rows: int = 5000

class VoltageStabilizationConfig(BaseModel):
    sample_interval_sec: float = 1.0
    stable_window_sec: float = 10.0
    tolerance_percent: float = 5.0
    phase_imbalance_tolerance_percent: float = 5.0
    timeout_sec: float = 60.0
    minimum_valid_voltage: float = 10.0

class ControlConfig(BaseModel):
    enabled: bool = True
    default_timeout_sec: float = 60.0
    off_grid_inter_source_delay_sec: float = 0.0
    use_mode_precondition_writes: bool = False
    voltage_stabilization: VoltageStabilizationConfig = Field(default_factory=VoltageStabilizationConfig)

class AppConfig(BaseModel):
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    existing_ems: ExistingEMSConfig = Field(default_factory=ExistingEMSConfig)
    external_ems_units: list[ExternalEMSUnitConfig] = Field(default_factory=list)
    register_map: RegisterMapConfig = Field(default_factory=RegisterMapConfig)
    decoding: DecodingConfig = Field(default_factory=DecodingConfig)
    polling: PollingConfig = Field(default_factory=PollingConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    logs_api: LogsAPIConfig = Field(default_factory=LogsAPIConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    server_upload: ServerUploadConfig = Field(default_factory=ServerUploadConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    control: ControlConfig = Field(default_factory=ControlConfig)

    def active_external_sources(self) -> list[ExternalEMSUnitConfig]:
        units = [u for u in self.external_ems_units if u.enabled]
        if units:
            return units
        return [ExternalEMSUnitConfig(
            source_id="existing_ems",
            display_name="Existing EMS",
            host=self.existing_ems.host,
            port=self.existing_ems.port,
            unit_id=self.existing_ems.unit_id,
            interface=self.network.field_interface,
            protocol=self.existing_ems.protocol,
            register_function=self.existing_ems.register_function,
            timeout_sec=self.existing_ems.timeout_sec,
            retries=self.existing_ems.retries,
        )]
