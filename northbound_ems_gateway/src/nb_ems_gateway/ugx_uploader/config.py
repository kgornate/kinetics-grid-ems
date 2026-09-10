from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .key_mapper import UGXKeyMappingConfig


@dataclass
class GatewayAPIConfig:
    base_url: str = "http://127.0.0.1:8000"
    username: str = "internal"
    password: str | None = None
    password_env: str | None = "NB_EMS_INTERNAL_PASSWORD"
    access_token: str | None = None
    access_token_env: str | None = None
    timeout_sec: float = 10.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GatewayAPIConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def resolved_password(self) -> str | None:
        if self.password_env and os.environ.get(self.password_env):
            return os.environ.get(self.password_env)
        return self.password

    def resolved_access_token(self) -> str | None:
        if self.access_token_env and os.environ.get(self.access_token_env):
            return os.environ.get(self.access_token_env)
        return self.access_token


@dataclass
class UGXServerConfig:
    base_url: str = "https://platform.uniqgrid.com"
    endpoint_template: str = "/api/v1/{deviceToken}/telemetry"
    device_token: str = "EMSTEST"
    timeout_sec: float = 15.0
    verify_tls: bool = True
    extra_headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UGXServerConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @property
    def telemetry_url(self) -> str:
        base = self.base_url.rstrip("/")
        path = self.endpoint_template.replace("{deviceToken}", self.device_token).lstrip("/")
        return f"{base}/{path}"


@dataclass
class FastBESSUploadConfig:
    enabled: bool = True
    db_path: str = "/mnt/ems-logs/northbound_ems_gateway/nb_ems_gateway.db"
    state_key: str = "fast_bess_compact"
    max_source_rows_per_cycle: int = 2000
    max_records_per_post: int = 500
    key_prefix: str = ""
    include_profile_metadata: bool = True
    include_quality_metadata: bool = True
    value_key_format: str = "{bess_id}_fast_{asset}_{signal}"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FastBESSUploadConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class FullPCSBMSUploadConfig:
    enabled: bool = True
    interval_sec: float = 60.0
    state_key: str = "full_pcs_bms_snapshot"
    max_asset_page_size: int = 500
    key_prefix: str = ""
    include_quality_metadata: bool = False
    value_key_format: str = "{bess_id}_full_{asset}_{signal}"
    sources: dict[str, dict[str, str]] = field(default_factory=lambda: {
        "external_ems_1": {
            "bess_id": "bess_1",
            "pcs_asset_id": "external_ems_1_pcs",
            "bms_asset_id": "external_ems_1_bms",
        },
        "external_ems_2": {
            "bess_id": "bess_2",
            "pcs_asset_id": "external_ems_2_pcs",
            "bms_asset_id": "external_ems_2_bms",
        },
    })

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FullPCSBMSUploadConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class UGXFrequencyUploadConfig:
    """Frequency-based UGX upload built from full PCS+BMS snapshots.

    The key plan from UGX separates telemetry into 1s, 60s, 900s, 3600s,
    and on-change/static groups. U1.2 uses this configuration to post only
    the keys due for a given frequency instead of sending one huge full
    snapshot every cycle.
    """

    enabled: bool = False
    state_key_prefix: str = "ugx_frequency"
    key_plan_path: str = "data/ugx/key_frequency_plan_v1.json"
    enabled_frequencies_sec: list[int] = field(default_factory=lambda: [60, 900])
    # 3600 contains the very heavy cell/rack diagnostic profile. It is
    # implemented but guarded by this flag so first rollout can validate the
    # 60s and 900s profiles without large payload bursts.
    allow_large_3600_upload: bool = False
    include_null_keys: bool = False
    always_include_time_fields: bool = True
    post_empty_profiles: bool = False
    max_keys_per_post: int = 2500
    profile_name: str = "uniqgrid_frequency_v1_2"
    # Allows a local desired upload cadence to reuse a key group from the UGX
    # frequency plan. Example: {"300": 900} posts the 900s key set every 300s.
    frequency_key_aliases: dict[str, int] = field(default_factory=lambda: {"300": 900})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UGXFrequencyUploadConfig":
        if not data:
            return cls()
        clean = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        if "enabled_frequencies_sec" in clean and clean["enabled_frequencies_sec"] is not None:
            clean["enabled_frequencies_sec"] = [int(v) for v in clean["enabled_frequencies_sec"]]
        return cls(**clean)


@dataclass
class UGXCombinedUploadConfig:
    """U1.3 combined-post upload mode.

    This mode buffers/gathers all due telemetry profiles inside the gateway
    process and sends one consolidated timestamped-array payload to the single
    UGX telemetry endpoint per upload window. It reduces cloud POST count while
    preserving the same payload schema accepted by UGX: list[{ts, values}].
    """

    enabled: bool = False
    state_key: str = "ugx_combined_cloud_post"
    cloud_post_interval_sec: float = 60.0
    include_fast_bess: bool = True
    include_frequency_profiles: bool = True
    # Safety guard. Combined upload is meant to send one POST; if payload exceeds
    # this threshold, the cycle fails without advancing pointers so the operator
    # can lower fast-history batch size or increase upload interval consciously.
    max_records_per_post: int = 500
    max_payload_bytes: int = 5_000_000
    record_profile: str = "ugx_combined_v1_3"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UGXCombinedUploadConfig":
        if not data:
            return cls()
        clean = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**clean)


@dataclass
class UploaderConfig:
    enabled: bool = True
    dry_run: bool = True
    run_interval_sec: float = 5.0
    failed_retry_interval_sec: float = 30.0
    state_db_path: str = "/mnt/ems-logs/northbound_ems_gateway/ugx_uploader_state.db"
    log_payload_preview: bool = True
    key_aliases: dict[str, str] = field(default_factory=dict)
    ugx_key_mapping: UGXKeyMappingConfig = field(default_factory=UGXKeyMappingConfig)
    ugx_server: UGXServerConfig = field(default_factory=UGXServerConfig)
    gateway_api: GatewayAPIConfig = field(default_factory=GatewayAPIConfig)
    fast_bess_upload: FastBESSUploadConfig = field(default_factory=FastBESSUploadConfig)
    full_pcs_bms_upload: FullPCSBMSUploadConfig = field(default_factory=FullPCSBMSUploadConfig)
    ugx_frequency_upload: UGXFrequencyUploadConfig = field(default_factory=UGXFrequencyUploadConfig)
    ugx_combined_upload: UGXCombinedUploadConfig = field(default_factory=UGXCombinedUploadConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UploaderConfig":
        return cls(
            enabled=bool(data.get("enabled", True)),
            dry_run=bool(data.get("dry_run", True)),
            run_interval_sec=float(data.get("run_interval_sec", 5.0)),
            failed_retry_interval_sec=float(data.get("failed_retry_interval_sec", 30.0)),
            state_db_path=str(data.get("state_db_path", "/mnt/ems-logs/northbound_ems_gateway/ugx_uploader_state.db")),
            log_payload_preview=bool(data.get("log_payload_preview", True)),
            key_aliases=dict(data.get("key_aliases") or {}),
            ugx_key_mapping=UGXKeyMappingConfig.from_dict(data.get("ugx_key_mapping") or {}),
            ugx_server=UGXServerConfig.from_dict(data.get("ugx_server") or {}),
            gateway_api=GatewayAPIConfig.from_dict(data.get("gateway_api") or {}),
            fast_bess_upload=FastBESSUploadConfig.from_dict(data.get("fast_bess_upload") or {}),
            full_pcs_bms_upload=FullPCSBMSUploadConfig.from_dict(data.get("full_pcs_bms_upload") or {}),
            ugx_frequency_upload=UGXFrequencyUploadConfig.from_dict(data.get("ugx_frequency_upload") or {}),
            ugx_combined_upload=UGXCombinedUploadConfig.from_dict(data.get("ugx_combined_upload") or {}),
        )


def load_uploader_config(path: str | Path) -> UploaderConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return UploaderConfig.from_dict(data)
