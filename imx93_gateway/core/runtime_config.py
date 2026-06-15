"""
Runtime configuration loader for the EMS gateway.

Design goal:
- Keep config.py and existing CLI arguments working exactly as before.
- Add an optional profile/config-file layer for lab, field, mock, and customer
  deployments.
- Add optional EMS_* environment variable overrides for deployment scripts.
- Keep command-line arguments as the highest-priority runtime overrides.

Precedence, lowest to highest:
    1. Built-in defaults passed by the caller
    2. config.py values
    3. optional JSON config file (--config-file or EMS_CONFIG_FILE)
    4. EMS_* environment variables
    5. existing CLI arguments handled by main.py

The module intentionally uses only Python standard library modules so it works
on the i.MX93 target without adding dependencies such as PyYAML.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional


JsonDict = Dict[str, Any]


def _is_public_config_name(name: str) -> bool:
    return name.isupper() and not name.startswith("_")


def _module_to_dict(config_module: Any) -> JsonDict:
    if config_module is None:
        return {}
    return {
        name: getattr(config_module, name)
        for name in dir(config_module)
        if _is_public_config_name(name)
    }


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enabled", "enable"}:
        return True
    if text in {"0", "false", "no", "off", "disabled", "disable"}:
        return False
    raise ValueError(f"Cannot parse boolean value: {value!r}")


def _coerce_like(value: Any, reference: Any) -> Any:
    """Coerce environment/file strings to the type used by config.py."""
    if reference is None:
        return value
    if isinstance(reference, bool):
        return _parse_bool(value)
    if isinstance(reference, int) and not isinstance(reference, bool):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    if isinstance(reference, set):
        if isinstance(value, str):
            return {item.strip().upper() for item in value.split(",") if item.strip()}
        if isinstance(value, Iterable):
            return {str(item).strip().upper() for item in value if str(item).strip()}
        return reference
    if isinstance(reference, tuple):
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        if isinstance(value, Iterable):
            return tuple(value)
        return reference
    if isinstance(reference, list):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, Iterable):
            return list(value)
        return reference
    if isinstance(reference, dict):
        if isinstance(value, str):
            return json.loads(value)
        return value
    return value


def _normalize_key(key: str) -> str:
    return str(key).strip().upper().replace("-", "_")


def _flatten_profile_mapping(data: Mapping[str, Any]) -> JsonDict:
    """
    Convert a JSON profile into config-style keys.

    Preferred format is flat uppercase keys:
        {"PCS_HOST": "192.168.1.200"}

    A small nested format is also accepted for readability:
        {"pcs": {"host": "192.168.1.200"}}

    The nested mapper is intentionally conservative and maps only the current
    gateway domains. Unknown nested groups are flattened as GROUP_KEY.
    """

    group_prefix = {
        "gateway": "",
        "chiller": "CHILLER_",
        "modbus": "MODBUS_",
        "pcs": "PCS_",
        "bms": "BMS_",
        "network": "",
        "logging": "LOG_",
        "log_http": "LOG_HTTP_",
        "web_api": "WEB_API_",
        "storage": "",
    }
    key_aliases = {
        "gateway.gateway_id": "GATEWAY_ID",
        "gateway.asset_id": "ASSET_ID",
        "chiller.enabled": "CHILLER_ENABLED",
        "chiller.asset_id": "ASSET_ID",
        "chiller.slave_id": "CHILLER_SLAVE_ID",
        "chiller.poll_interval_sec": "CHILLER_POLL_INTERVAL_SEC",
        "pcs.host": "PCS_HOST",
        "pcs.port": "PCS_PORT",
        "pcs.unit_id": "PCS_UNIT_ID",
        "pcs.vendor": "PCS_VENDOR",
        "pcs.enabled": "PCS_ENABLED",
        "pcs.asset_id": "PCS_ASSET_ID",
        "pcs.poll_interval_sec": "PCS_POLL_INTERVAL_SEC",
        "bms.host": "BMS_MODBUS_HOST",
        "bms.port": "BMS_MODBUS_PORT",
        "bms.unit_id": "BMS_UNIT_ID",
        "bms.enabled": "BMS_ENABLED",
        "bms.asset_id": "BMS_ASSET_ID",
        "bms.poll_interval_sec": "BMS_POLL_INTERVAL_SEC",
        "network.pc_telemetry_ip": "PC_TELEMETRY_IP",
        "network.udp_telemetry_port": "UDP_TELEMETRY_PORT",
        "network.tcp_command_host": "TCP_COMMAND_HOST",
        "network.tcp_command_port": "TCP_COMMAND_PORT",
        "logging.base_path": "LOG_BASE_PATH",
        "logging.telemetry_interval_sec": "LOG_TELEMETRY_INTERVAL_SEC",
        "storage.enable_storage_logging": "ENABLE_STORAGE_LOGGING",
        "log_http.enabled": "ENABLE_LOG_HTTP_SERVER",
        "log_http.host": "LOG_HTTP_HOST",
        "log_http.port": "LOG_HTTP_PORT",
        "log_http.max_rows": "LOG_API_MAX_ROWS",
        "web_api.enabled": "ENABLE_WEB_API_SERVER",
        "web_api.host": "WEB_API_HOST",
        "web_api.port": "WEB_API_PORT",
        "web_api.enable_auth": "WEB_API_ENABLE_AUTH",
        "web_api.key": "WEB_API_KEY",
        "web_api.cors_allow_origin": "WEB_API_CORS_ALLOW_ORIGIN",
        "web_api.telemetry_stream_interval_sec": "WEB_API_TELEMETRY_STREAM_INTERVAL_SEC",
    }

    flattened: JsonDict = {}

    def add(path: str, value: Any) -> None:
        path_parts = path.split(".")
        alias = key_aliases.get(path)
        if alias:
            flattened[alias] = value
            return
        if len(path_parts) == 1:
            flattened[_normalize_key(path_parts[0])] = value
            return
        group = path_parts[0]
        suffix = "_".join(path_parts[1:])
        prefix = group_prefix.get(group, f"{group.upper()}_")
        flattened[_normalize_key(prefix + suffix)] = value

    def walk(prefix: str, value: Any) -> None:
        if isinstance(value, Mapping):
            for child_key, child_value in value.items():
                child_path = f"{prefix}.{child_key}" if prefix else str(child_key).strip().lower()
                walk(child_path, child_value)
        else:
            add(prefix, value)

    walk("", data)
    return flattened


def _load_json_file(path: Path) -> JsonDict:
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, Mapping):
        raise ValueError(f"Runtime config file must contain a JSON object: {path}")
    return _flatten_profile_mapping(raw)


def _derive_asset_legacy_overrides(values: Mapping[str, Any]) -> JsonDict:
    """
    Convert optional ASSETS list into legacy flat config keys.

    This keeps the current chiller/PCS/BMS service startup code working while
    letting deployments move toward an asset-list config model. The import is
    intentionally local to avoid making runtime_config depend on asset modules
    during early interpreter startup.
    """
    raw_assets = values.get("ASSETS") if isinstance(values, Mapping) else None
    if not raw_assets:
        return {}
    try:
        from core.assets.asset_profile import AssetConfigRegistry

        return AssetConfigRegistry.from_raw_assets(raw_assets).legacy_overrides()
    except Exception as error:
        raise ValueError(f"Invalid ASSETS config: {error}") from error


@dataclass
class RuntimeConfig:
    values: JsonDict = field(default_factory=dict)
    source_map: Dict[str, str] = field(default_factory=dict)
    config_file: Optional[str] = None
    env_prefix: str = "EMS_"

    def get(self, name: str, default: Any = None) -> Any:
        key = _normalize_key(name)
        value = self.values.get(key, default)
        if value is not default:
            value = _coerce_like(value, default)
        return value

    def source_of(self, name: str) -> str:
        return self.source_map.get(_normalize_key(name), "default")

    def update_from_mapping(self, mapping: Mapping[str, Any], *, source: str) -> None:
        for key, value in mapping.items():
            norm_key = _normalize_key(key)
            existing = self.values.get(norm_key)
            try:
                value = _coerce_like(value, existing)
            except Exception:
                # Keep raw value so a later caller can still decide how to handle it.
                pass
            self.values[norm_key] = value
            self.source_map[norm_key] = source

    def to_safe_dict(self) -> JsonDict:
        safe: JsonDict = {}
        for key, value in sorted(self.values.items()):
            if "KEY" in key or "SECRET" in key or "TOKEN" in key or "PASSWORD" in key:
                safe[key] = "***"
            elif isinstance(value, set):
                safe[key] = sorted(value)
            else:
                safe[key] = value
        return safe

    def get_status(self) -> JsonDict:
        active_sources = sorted(set(self.source_map.values()))
        return {
            "config_class": self.__class__.__name__,
            "config_file": self.config_file,
            "env_prefix": self.env_prefix,
            "active_sources": active_sources,
            "value_count": len(self.values),
        }


def load_runtime_config(args: Any, config_module: Any = None, *, env: Optional[Mapping[str, str]] = None) -> RuntimeConfig:
    if env is None:
        env = os.environ
    runtime_config = RuntimeConfig()

    module_values = _module_to_dict(config_module)
    runtime_config.update_from_mapping(module_values, source="config.py")

    config_file = getattr(args, "config_file", None) or env.get("EMS_CONFIG_FILE")
    if config_file:
        config_path = Path(config_file).expanduser().resolve()
        profile_values = _load_json_file(config_path)
        runtime_config.config_file = str(config_path)
        runtime_config.update_from_mapping(profile_values, source=f"config_file:{config_path.name}")

        asset_overrides = _derive_asset_legacy_overrides(runtime_config.values)
        if asset_overrides:
            runtime_config.update_from_mapping(
                asset_overrides,
                source=f"asset_list:{config_path.name}",
            )

    env_values: JsonDict = {}
    prefix = runtime_config.env_prefix
    for env_key, env_value in env.items():
        if not env_key.startswith(prefix):
            continue
        config_key = env_key[len(prefix):]
        if not config_key or config_key == "CONFIG_FILE":
            continue
        env_values[config_key] = env_value
    if env_values:
        runtime_config.update_from_mapping(env_values, source="environment")

    return runtime_config
