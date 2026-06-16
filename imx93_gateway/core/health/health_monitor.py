"""Gateway health and diagnostics model.

Health output is intentionally separate from telemetry. Telemetry tells the
operator the latest values. Health tells whether those values are fresh and
trustworthy, why an asset is unhealthy, and what action to take next.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.assets import RuntimeAssetCatalog

JsonDict = Dict[str, Any]
StorageHealthProvider = Callable[[str], Optional[JsonDict]]


class HealthMonitor:
    """Build health and diagnostics responses from gateway status/telemetry."""

    ASSET_KEYS = ("chiller", "pcs", "bms")

    def __init__(
        self,
        *,
        status_packet: JsonDict,
        telemetry_packet: Optional[JsonDict] = None,
        storage_health_provider: Optional[StorageHealthProvider] = None,
    ):
        self.status_packet = status_packet if isinstance(status_packet, dict) else {}
        self.telemetry_packet = telemetry_packet if isinstance(telemetry_packet, dict) else {}
        self.storage_health_provider = storage_health_provider
        self.asset_catalog = RuntimeAssetCatalog.from_packets(
            status_packet=self.status_packet,
            telemetry_packet=self.telemetry_packet,
        )

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    @staticmethod
    def normalize_asset_key(asset_id: str) -> str:
        return RuntimeAssetCatalog.normalize_asset_key(asset_id)

    def build_gateway_health(self) -> JsonDict:
        asset_health = self.build_assets_health()
        counts = asset_health.get("summary", {})
        status = "healthy"
        if counts.get("offline", 0) > 0:
            status = "offline"
        elif counts.get("degraded", 0) > 0 or counts.get("unknown", 0) > 0:
            status = "degraded"

        web_api = self.status_packet.get("web_api", {}) if isinstance(self.status_packet.get("web_api"), dict) else {}
        log_http = self.status_packet.get("log_http", {}) if isinstance(self.status_packet.get("log_http"), dict) else {}
        udp = self.status_packet.get("udp_streamer", {}) if isinstance(self.status_packet.get("udp_streamer"), dict) else None
        tcp = self.status_packet.get("tcp_server", {}) if isinstance(self.status_packet.get("tcp_server"), dict) else None

        return {
            "status": status,
            "gateway_id": self.status_packet.get("gateway_id"),
            "timestamp": self.now_iso(),
            "mode": self.status_packet.get("mode"),
            "summary": counts,
            "services": {
                "web_api": self._service_health("web_api", web_api.get("enabled", True), web_api.get("running"), web_api),
                "log_http": self._service_health("log_http", log_http.get("enabled", True), bool(log_http), log_http),
                "udp_streamer": self._service_health("udp_streamer", udp is not None, udp.get("running") if isinstance(udp, dict) else False, udp or {}),
                "tcp_server": self._service_health("tcp_server", tcp is not None, tcp.get("running") if isinstance(tcp, dict) else False, tcp or {}),
            },
            "recommended_action": self._gateway_recommendation(status, counts),
        }

    def build_assets_health(self) -> JsonDict:
        assets: Dict[str, JsonDict] = {}
        counts = {"total": 0, "healthy": 0, "degraded": 0, "offline": 0, "disabled": 0, "unknown": 0}
        for record in self.asset_catalog.records:
            item = self.build_asset_health(record.asset_id)
            asset_id = item.get("asset_id") or record.asset_id
            assets[str(asset_id)] = item
            counts["total"] += 1
            counts[item.get("status", "unknown")] = counts.get(item.get("status", "unknown"), 0) + 1
        return {
            "status": "ok",
            "timestamp": self.now_iso(),
            "summary": counts,
            "assets": assets,
        }

    def build_asset_health(self, asset_id: str) -> JsonDict:
        record = self.asset_catalog.find(asset_id)
        asset_key = record.asset_key if record else self.normalize_asset_key(asset_id)
        status_section = self.status_packet.get(asset_key, {})
        if not isinstance(status_section, dict):
            status_section = {}
        telemetry = self._extract_asset_packet(asset_key)

        if record is not None:
            enabled = record.enabled
            running = record.running
            resolved_asset_id = record.asset_id
            asset_type = record.asset_type
        else:
            enabled = bool(status_section.get("enabled", telemetry is not None))
            running = bool(status_section.get("running", telemetry is not None))
            resolved_asset_id = str(status_section.get("asset_id") or self._asset_id_from_key(asset_key))
            asset_type = status_section.get("asset_type") or asset_key

        if not enabled:
            status = "disabled"
            reason = "Asset is disabled by configuration or command-line option."
        elif not running and record is not None and record.runtime_mode == "configured_future":
            status = "unknown"
            reason = "Asset is configured for a future runtime integration but no active service is running."
        elif not running:
            status = "offline"
            reason = "Asset service is enabled but not running."
        else:
            status, reason = self._asset_status_from_telemetry(asset_key, telemetry, status_section)

        storage_health = self._safe_storage_health(resolved_asset_id)
        if status == "healthy" and isinstance(storage_health, dict):
            storage_status = str(storage_health.get("status", "")).lower()
            if storage_status in {"degraded", "offline", "error"}:
                status = "degraded"
                reason = f"Asset communication is healthy but storage is {storage_status}."

        last_success, last_error, consecutive_failures = self._extract_failure_details(status_section, telemetry)

        return {
            "status": status,
            "asset_id": resolved_asset_id,
            "asset_key": asset_key,
            "asset_type": asset_type,
            "enabled": enabled,
            "running": running,
            "online": status == "healthy",
            "runtime_mode": record.runtime_mode if record else ("active_service" if running else "disabled" if not enabled else "configured_only"),
            "protocol": (record.protocol if record else None) or status_section.get("protocol"),
            "profile": (record.profile if record else None) or status_section.get("profile"),
            "vendor": (record.vendor if record else None) or status_section.get("vendor"),
            "connection": record.connection if record else self._connection_summary(status_section),
            "last_successful_poll": last_success,
            "last_error": last_error,
            "consecutive_failures": consecutive_failures,
            "reason": reason,
            "recommended_action": self._asset_recommendation(asset_key, status, status_section, last_error),
            "storage": storage_health,
            "timestamp": self.now_iso(),
        }

    def build_diagnostics(self, asset_id: Optional[str] = None) -> JsonDict:
        if asset_id:
            health = self.build_asset_health(asset_id)
            return {
                "status": "ok",
                "timestamp": self.now_iso(),
                "asset_id": health.get("asset_id"),
                "diagnostics": self._diagnostics_from_health(health),
                "health": health,
            }

        assets = self.build_assets_health().get("assets", {})
        diagnostics = {asset_id: self._diagnostics_from_health(health) for asset_id, health in assets.items()}
        gateway = self.build_gateway_health()
        return {
            "status": "ok",
            "timestamp": self.now_iso(),
            "gateway": gateway,
            "diagnostics": diagnostics,
        }

    def build_overall_health(self) -> JsonDict:
        gateway = self.build_gateway_health()
        assets = self.build_assets_health()
        status = gateway.get("status", "unknown")
        return {
            "status": status,
            "timestamp": self.now_iso(),
            "gateway_id": self.status_packet.get("gateway_id"),
            "gateway": gateway,
            "assets": assets.get("assets", {}),
            "summary": assets.get("summary", {}),
        }

    def _service_health(self, name: str, enabled: bool, running: Any, details: JsonDict) -> JsonDict:
        if not enabled:
            status = "disabled"
        elif bool(running):
            status = "healthy"
        else:
            status = "offline"
        return {
            "status": status,
            "enabled": bool(enabled),
            "running": bool(running),
            "details": details,
        }

    def _extract_asset_packet(self, asset_key: str) -> Optional[JsonDict]:
        _, packet = RuntimeAssetCatalog.extract_asset_packet(asset_key, self.telemetry_packet)
        return packet

    def _asset_id_from_key(self, asset_key: str) -> str:
        record = self.asset_catalog.find(asset_key)
        if record is not None:
            return record.asset_id
        if asset_key == "pcs":
            return "pcs_1"
        if asset_key == "bms":
            return "bms_1"
        if asset_key == "chiller":
            return "chiller_1"
        return asset_key

    def _asset_status_from_telemetry(self, asset_key: str, telemetry: Optional[JsonDict], status_section: JsonDict) -> Tuple[str, str]:
        if telemetry is None:
            return "unknown", "No telemetry packet is available yet."

        status_texts: List[str] = []
        for key in ["status", "communication_status", "comm_status", "modbus_status", "logger_status"]:
            value = telemetry.get(key)
            if value is not None:
                status_texts.append(str(value).lower())
        data = telemetry.get("data")
        if isinstance(data, dict):
            for key in ["status", "communication_status", "comm_status", "modbus_status", "logger_status"]:
                value = data.get(key)
                if value is not None:
                    status_texts.append(str(value).lower())

        if any(text in {"offline", "lost", "failed", "failure"} for text in status_texts):
            return "offline", "Telemetry reports communication offline or failed."
        if any(text in {"error", "warning", "degraded"} for text in status_texts):
            return "degraded", "Telemetry reports warning, degraded, or error status."
        if any(text in {"ok", "online", "connected", "success", "healthy", "mock"} for text in status_texts):
            return "healthy", "Asset service is running and latest telemetry looks healthy."
        if status_section.get("running"):
            return "healthy", "Asset service is running; no unhealthy telemetry status detected."
        return "unknown", "Unable to determine asset health from current telemetry."

    def _extract_failure_details(self, status_section: JsonDict, telemetry: Optional[JsonDict]) -> Tuple[Optional[Any], Optional[Any], int]:
        candidates = [status_section]
        if isinstance(status_section.get("state"), dict):
            candidates.append(status_section["state"])
        if isinstance(telemetry, dict):
            candidates.append(telemetry)
            if isinstance(telemetry.get("data"), dict):
                candidates.append(telemetry["data"])

        last_success = None
        last_error = None
        failures = 0
        for item in candidates:
            last_success = last_success or item.get("last_success_ts") or item.get("last_successful_poll") or item.get("last_update_time") or item.get("timestamp")
            last_error = last_error or item.get("last_error") or item.get("error") or item.get("fault_description")
            for key in ["consecutive_failures", "failure_count", "consecutive_error_count"]:
                if item.get(key) is not None:
                    try:
                        failures = max(failures, int(item.get(key)))
                    except Exception:
                        pass
        return last_success, last_error, failures

    def _connection_summary(self, status_section: JsonDict) -> JsonDict:
        out: JsonDict = {}
        for key in ["host", "port", "unit_id", "serial_port", "baudrate", "protocol"]:
            if status_section.get(key) is not None:
                out[key] = status_section.get(key)
        return out

    def _safe_storage_health(self, asset_id: str) -> Optional[JsonDict]:
        if self.storage_health_provider is None:
            return None
        try:
            result = self.storage_health_provider(asset_id)
            return result if isinstance(result, dict) else None
        except Exception as error:
            return {"status": "degraded", "error": str(error)}

    def _gateway_recommendation(self, status: str, counts: JsonDict) -> str:
        if status == "healthy":
            return "No immediate action required."
        if counts.get("offline", 0) > 0:
            return "Check offline assets, network links, simulator/field device power, IP/port configuration, and firewall settings."
        if counts.get("degraded", 0) > 0:
            return "Review degraded asset diagnostics and storage health details."
        return "Review gateway status and latest telemetry."

    def _asset_recommendation(self, asset_key: str, status: str, status_section: JsonDict, last_error: Optional[Any]) -> str:
        if status == "healthy":
            return "No immediate action required."
        if status == "disabled":
            return "Enable the asset in config or remove the disable flag if this asset should run."
        if asset_key in {"pcs", "bms"}:
            host = status_section.get("host")
            port = status_section.get("port")
            return f"Check {asset_key.upper()} device/simulator at {host}:{port}, network route, firewall, and unit ID."
        if asset_key == "chiller":
            return "Check RS485 wiring, USB/serial adapter, chiller power, slave ID, and baudrate."
        if last_error:
            return f"Review last error: {last_error}"
        return "Review asset configuration and communication link."

    def _diagnostics_from_health(self, health: JsonDict) -> JsonDict:
        status = health.get("status", "unknown")
        severity = {
            "healthy": "info",
            "disabled": "info",
            "unknown": "warning",
            "degraded": "warning",
            "offline": "critical",
        }.get(str(status), "warning")
        return {
            "severity": severity,
            "status": status,
            "reason": health.get("reason"),
            "last_error": health.get("last_error"),
            "recommended_action": health.get("recommended_action"),
            "connection": health.get("connection"),
            "storage_status": (health.get("storage") or {}).get("status") if isinstance(health.get("storage"), dict) else None,
        }
