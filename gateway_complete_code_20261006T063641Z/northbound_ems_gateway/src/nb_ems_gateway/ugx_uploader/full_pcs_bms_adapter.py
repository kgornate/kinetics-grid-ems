from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from .api_client import LocalGatewayAPIClient
from .config import FullPCSBMSUploadConfig, UploaderConfig

LOG = logging.getLogger(__name__)


def _safe_value(value: Any) -> Any:
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)


class FullPCSBMSAdapter:
    def __init__(self, config: UploaderConfig) -> None:
        self.root_config = config
        self.config: FullPCSBMSUploadConfig = config.full_pcs_bms_upload
        self.api = LocalGatewayAPIClient(config.gateway_api)

    def build_snapshot_record(self) -> dict[str, Any]:
        ts_ms = int(time.time() * 1000)
        values: dict[str, Any] = {
            "northbound_full_snapshot_time_utc": datetime.now(timezone.utc).isoformat(),
            "northbound_full_snapshot_ts": ts_ms,
        }
        for source_id, mapping in self.config.sources.items():
            bess_id = mapping.get("bess_id") or source_id
            for asset_kind, asset_id_key in [("pcs", "pcs_asset_id"), ("bms", "bms_asset_id")]:
                asset_id = mapping.get(asset_id_key)
                if not asset_id:
                    continue
                signals = self._read_all_asset_signals(asset_id)
                for signal_name, signal in signals.items():
                    key = self._key(bess_id, asset_kind, signal_name)
                    values[key] = _safe_value(signal.get("value"))
                    if self.config.include_quality_metadata:
                        values[f"{key}__quality"] = _safe_value(signal.get("quality"))
                values[self._key(bess_id, asset_kind, "signal_count")] = len(signals)
        return {"ts": ts_ms, "values": values}

    def _read_all_asset_signals(self, asset_id: str) -> dict[str, dict[str, Any]]:
        page = 1
        page_size = max(1, min(int(self.config.max_asset_page_size), 500))
        all_signals: dict[str, dict[str, Any]] = {}
        while True:
            data = self.api.get_json(
                f"/api/assets/{asset_id}/telemetry",
                params={"compact": "true", "page": page, "page_size": page_size},
            )
            signals = data.get("signals") or {}
            all_signals.update(signals)
            pagination = data.get("pagination") or {}
            if not pagination.get("has_more"):
                break
            page += 1
            if page > 20:
                raise RuntimeError(f"too many pages while reading {asset_id}; stopping at page {page}")
        return all_signals

    def _key(self, bess_id: str, asset: str, signal: str) -> str:
        raw = self.config.value_key_format.format(bess_id=bess_id, asset=asset, signal=signal)
        key = f"{self.config.key_prefix}{raw}"
        return self.root_config.key_aliases.get(key, key)
