from __future__ import annotations

from pydantic import BaseModel, Field


class GatewayConfig(BaseModel):
    id: str = "northbound_ems_gateway"
    name: str = "NorthBound EMS Gateway"
    mode: str = "read_only"


class NetworkConfig(BaseModel):
    field_interface: str = "eth1"
    application_interface: str = "eth0"


class ExistingEMSConfig(BaseModel):
    protocol: str = "modbus_tcp"
    host: str
    port: int = 515
    unit_id: int = 1
    register_function: str = "holding_registers"
    timeout_sec: float = 2.0
    retries: int = 2


class RegisterMapConfig(BaseModel):
    path: str = "data/register_maps/china_ems_northbound_v1.json"


class DecodingConfig(BaseModel):
    data_type: str = "float32"
    registers_per_point: int = 2
    byte_order: str = "ABCD"
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


class StorageConfig(BaseModel):
    enabled: bool = True
    type: str = "sqlite"
    path: str = "runtime/nb_ems_gateway.db"


class ServerUploadConfig(BaseModel):
    enabled: bool = False
    transport: str = "https_or_mqtt_future"
    buffer_when_offline: bool = True


class AppConfig(BaseModel):
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    existing_ems: ExistingEMSConfig
    register_map: RegisterMapConfig = Field(default_factory=RegisterMapConfig)
    decoding: DecodingConfig = Field(default_factory=DecodingConfig)
    polling: PollingConfig = Field(default_factory=PollingConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    server_upload: ServerUploadConfig = Field(default_factory=ServerUploadConfig)

    def assert_read_only(self) -> None:
        if self.gateway.mode != "read_only":
            raise ValueError("Version 1 supports only gateway.mode='read_only'.")
        if self.api.commands_enabled:
            raise ValueError("Command APIs are disabled in read-only Version 1.")
