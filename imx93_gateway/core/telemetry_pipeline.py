"""
Telemetry pipeline for the EMS gateway.

Design goal:
- Move asset telemetry collection out of main.py.
- Preserve the existing legacy UDP/Web API packet shape used by Flutter and
  the web dashboard.
- Add a canonical internal snapshot that future code can use without changing
  current external contracts.

This module does not read Modbus directly. It asks registered asset adapters for
telemetry and only falls back to legacy service callbacks if an adapter is not
available. That keeps Telemetry-pipeline safe for the existing working system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional

from core.telemetry_composer import compose_legacy_udp_packet, now_iso, offline_asset_packet


JsonDict = Dict[str, Any]
AdapterGetter = Callable[[str], Optional[Any]]
ModeProvider = Callable[[], str]
TelemetryFallback = Callable[[], Optional[JsonDict]]


@dataclass(frozen=True)
class TelemetryPipelineConfig:
    """Static identifiers needed to build telemetry packets."""

    gateway_id: str
    chiller_asset_id: str
    pcs_asset_id: str
    bms_asset_id: str
    pcs_vendor: str = "njoy"


class TelemetryPipeline:
    """
    Build gateway telemetry from asset adapters while preserving legacy output.

    External clients still receive the same packet returned by
    compose_legacy_udp_packet(). Internally, this creates a canonical
    `snapshot` first so future extensions can move APIs/logging/UI to one consistent
    asset-indexed structure without touching Modbus services again.
    """

    ASSET_TYPES = {
        "chiller": "chiller",
        "pcs": "pcs",
        "bms": "bms",
    }

    def __init__(
        self,
        *,
        config: TelemetryPipelineConfig,
        get_asset_adapter: AdapterGetter,
        get_mode: ModeProvider,
        fallbacks: Optional[Mapping[str, TelemetryFallback]] = None,
    ):
        self.config = config
        self.get_asset_adapter = get_asset_adapter
        self.get_mode = get_mode
        self.fallbacks = dict(fallbacks or {})

    def get_legacy_udp_packet(self) -> JsonDict:
        """
        Return the existing Flutter/Web compatible mixed telemetry packet.

        This is the only method main.py should need for the current UDP streamer
        and EMS Web API callback.
        """
        snapshot = self.build_snapshot()
        packets = snapshot["assets"]
        return compose_legacy_udp_packet(
            gateway_id=self.config.gateway_id,
            mode=snapshot["mode"],
            chiller_asset_id=self.config.chiller_asset_id,
            pcs_asset_id=self.config.pcs_asset_id,
            bms_asset_id=self.config.bms_asset_id,
            chiller_packet=packets.get("chiller"),
            pcs_packet=packets.get("pcs"),
            bms_packet=packets.get("bms"),
            timestamp=snapshot["timestamp"],
        )

    def build_snapshot(self) -> JsonDict:
        """
        Build a canonical internal snapshot.

        This shape is additive/internal. It is exposed only inside
        gateway status diagnostics and tests, not used as a replacement for the
        legacy UDP/Web API packet yet.
        """
        timestamp = now_iso()
        mode = self.get_mode()

        chiller_packet = self._collect_asset_packet(
            asset_key="chiller",
            asset_id=self.config.chiller_asset_id,
            asset_type="chiller",
            timestamp=timestamp,
        )
        pcs_packet = self._collect_asset_packet(
            asset_key="pcs",
            asset_id=self.config.pcs_asset_id,
            asset_type="pcs",
            timestamp=timestamp,
        )
        if isinstance(pcs_packet, dict) and pcs_packet.get("comm_status") == "offline":
            pcs_packet.setdefault("vendor", self.config.pcs_vendor)

        bms_packet = self._collect_asset_packet(
            asset_key="bms",
            asset_id=self.config.bms_asset_id,
            asset_type="bms",
            timestamp=timestamp,
        )

        assets = {
            "chiller": chiller_packet,
            "pcs": pcs_packet,
            "bms": bms_packet,
        }

        online_count = 0
        available_count = 0
        for packet in assets.values():
            if packet is None:
                continue
            available_count += 1
            status_text = str(
                packet.get("communication_status")
                or packet.get("comm_status")
                or packet.get("status")
                or ""
            ).lower()
            if status_text in {"ok", "online", "mock", "running"}:
                online_count += 1

        return {
            "type": "telemetry_snapshot",
            "gateway_id": self.config.gateway_id,
            "timestamp": timestamp,
            "mode": mode,
            "assets": assets,
            "summary": {
                "configured_asset_keys": sorted(assets.keys()),
                "available_asset_count": available_count,
                "online_like_asset_count": online_count,
            },
        }

    def _collect_asset_packet(
        self,
        *,
        asset_key: str,
        asset_id: str,
        asset_type: str,
        timestamp: str,
    ) -> Optional[JsonDict]:
        adapter = self.get_asset_adapter(asset_key)
        if adapter is not None:
            try:
                return adapter.get_telemetry()
            except Exception as error:
                return self._offline_packet(
                    asset_id=asset_id,
                    asset_type=asset_type,
                    error=str(error),
                    timestamp=timestamp,
                )

        fallback = self.fallbacks.get(asset_key)
        if fallback is not None:
            try:
                return fallback()
            except Exception as error:
                return self._offline_packet(
                    asset_id=asset_id,
                    asset_type=asset_type,
                    error=str(error),
                    timestamp=timestamp,
                )

        return None

    def _offline_packet(
        self,
        *,
        asset_id: str,
        asset_type: str,
        error: str,
        timestamp: str,
    ) -> JsonDict:
        return offline_asset_packet(
            gateway_id=self.config.gateway_id,
            asset_id=asset_id,
            asset_type=asset_type,
            error=error,
            timestamp=timestamp,
        )

    def get_status(self) -> JsonDict:
        """Return additive diagnostics safe to expose in gateway status."""
        return {
            "pipeline_class": self.__class__.__name__,
            "gateway_id": self.config.gateway_id,
            "legacy_packet_function": "compose_legacy_udp_packet",
            "canonical_snapshot_type": "telemetry_snapshot",
            "asset_ids": {
                "chiller": self.config.chiller_asset_id,
                "pcs": self.config.pcs_asset_id,
                "bms": self.config.bms_asset_id,
            },
            "fallback_asset_keys": sorted(self.fallbacks.keys()),
        }
