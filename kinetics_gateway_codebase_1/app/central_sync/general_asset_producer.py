from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Iterable

from .config import CentralSyncConfig
from .contracts import utc_now_iso
from .local_gateway_api import LocalGatewayApiClient
from .outbox import OutboxCapacityError, OutboxStore
from .producer_common import ProducerCounters, ProducerLoopMixin, emit_message, fingerprint

S2_SUBSTREAMS = (
    "ems_system", "pcs_extended", "bms_extended", "io_module", "liquid_cooling",
    "fire_protection", "dehumidifier", "remote_control", "utility_meter",
)

# These raw points are represented in S1 through the normalized fast-pair view.
S1_CRITICAL_KEYS = {
    # Lineage rack/system
    "system_voltage", "system_current", "system_soc", "system_soh", "system_max_charge_power",
    "system_max_discharge_power", "system_max_charge_current", "system_max_discharge_current",
    "rack_voltage", "rack_current", "rack_soc", "rack_soh", "rack_max_charge_power",
    "rack_max_discharge_power", "rack_max_charge_current", "rack_max_discharge_current",
    "positive_contactor_feedback", "negative_contactor_feedback", "positive_insulation_resistance",
    "negative_insulation_resistance", "rack_max_cell_voltage", "rack_min_cell_voltage",
    "rack_max_cell_temperature", "rack_min_cell_temperature", "system_state", "rack_state",
    # Elecod
    "status_word", "total_active_power", "total_reactive_power", "total_power_factor",
    "dc_voltage", "dc_current", "dc_power", "dc_bus_voltage", "grid_frequency_a",
    "grid_voltage_ab", "grid_voltage_bc", "grid_voltage_ca",
}


def _load_points(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("points", [])
    return [dict(x) for x in payload if isinstance(x, dict)]


class CatalogIndex:
    def __init__(self, root: str | Path) -> None:
        root = Path(root)
        self.by_vendor_scope_key: dict[tuple[str, str, str], dict[str, Any]] = {}
        for vendor, name in (
            ("lineage", "lineage_bms_catalog.json"),
            ("elecod", "elecod_pcs_catalog.json"),
            ("kinetics_bms", "bms_catalog.json"),
            ("kinetics_pcs", "pcs_catalog.json"),
        ):
            for point in _load_points(root / name):
                key = str(point.get("key") or "")
                scope = str(point.get("scope") or "")
                if key and scope:
                    self.by_vendor_scope_key[(vendor, scope, key)] = point

    def get(self, vendor: str, scope: str, key: str) -> dict[str, Any] | None:
        return self.by_vendor_scope_key.get((vendor, scope, key))


def _vendor_tag(asset: dict[str, Any], vendors: dict[str, Any]) -> str:
    asset_type = str(asset.get("asset_type") or "").lower()
    aid = str(asset.get("asset_id") or "").lower()
    if "pcs" in asset_type or aid.startswith("pcs_"):
        v = str(vendors.get("pcs") or "kinetics").lower()
        return "elecod" if v == "elecod" else "kinetics_pcs"
    v = str(vendors.get("bms") or "kinetics").lower()
    return "lineage" if v == "lineage" else "kinetics_bms"


def _scope(asset: dict[str, Any]) -> str:
    aid = str(asset.get("asset_id") or "").lower()
    asset_type = str(asset.get("asset_type") or "").lower()
    if aid.startswith("pcs_") or "pcs" in asset_type:
        return "pcs"
    if aid.startswith("bms_rack_") or asset.get("rack_id") is not None:
        return "rack"
    if aid.startswith("bms_bank") or asset_type in {"bank", "bams", "system"}:
        return "bank"
    return "environment"


def _is_writable(point: dict[str, Any]) -> bool:
    access = str(point.get("access") or point.get("rw") or "R").upper()
    return "W" in access


def classify_substream(asset: dict[str, Any], key: str, point: dict[str, Any] | None) -> str:
    p = point or {}
    scope = _scope(asset)
    category = str(p.get("category") or "").lower()
    text = " ".join([key.lower(), category, str(p.get("name_en") or "").lower()])

    if _is_writable(p) or category in {"control", "control_parameter", "control_parameter_2", "remote_control", "setting", "communication_parameter", "rtc"}:
        return "remote_control"
    if category == "chiller" or "chiller" in text or "liquid cooling" in text:
        return "liquid_cooling"
    if category == "dehumidifier" or "dehumid" in text:
        return "dehumidifier"
    if any(token in text for token in ("fire_start", "fire fault", "fire_fault", "aerosol", "combustible_gas", "gas alarm", "emergency_stop")):
        return "fire_protection"
    if category in {"temp_humidity", "water_sensor"}:
        return "io_module"
    if scope == "environment":
        return "io_module"
    if scope == "pcs":
        return "pcs_extended"
    if scope == "bank" and category in {"system_data", "general", "status"}:
        return "ems_system"
    if scope == "bank" and category == "system_alarm":
        return "io_module"
    return "bms_extended"


def policy_for(point: dict[str, Any] | None) -> tuple[str, float, float, str, str, str]:
    p = point or {}
    poll_class = str(p.get("poll_class") or "normal").lower()
    category = str(p.get("category") or "").lower()
    writable = _is_writable(p)
    if writable or poll_class == "fast" or category in {"status", "alarm", "system_alarm", "rack_alarm"}:
        return "ON_CHANGE_HEARTBEAT", 30.0, 5.0, "High", "T2_1Y", "change_or_heartbeat"
    if poll_class == "bulk":
        return "BULK_30S", 30.0, 30.0, "Normal", "T1_90D", "periodic"
    if poll_class == "slow":
        return "SLOW_60S", 60.0, 60.0, "Normal", "T2_1Y", "periodic"
    return "NORMAL_5S", 5.0, 5.0, "Normal", "T1_90D", "periodic"


class GeneralAssetProducer(ProducerLoopMixin):
    """S2 producer emitting Northbound-compatible point records."""

    def __init__(self, *, config: CentralSyncConfig, outbox: OutboxStore, local_api: Any | None = None, catalog: CatalogIndex | None = None) -> None:
        self.config = config
        self.producer_config = config.general_assets
        self.outbox = outbox
        self.local_api = local_api or LocalGatewayApiClient(config.local_gateway_api)
        self._owns_api = local_api is None
        self.catalog = catalog or CatalogIndex(self.producer_config.catalog_dir)
        self.counters = ProducerCounters()
        self.running = False
        self.started_utc = utc_now_iso()
        self._stop = asyncio.Event()
        self._last_emit: dict[str, float] = {}
        self._last_fingerprint: dict[str, str] = {}

    async def close(self) -> None:
        if self._owns_api:
            await self.local_api.close()

    async def collect_once(self) -> dict[str, Any]:
        now_mono = time.monotonic()
        self.counters.poll_count += 1
        self.counters.last_poll_utc = utc_now_iso()
        snapshot = await self.local_api.telemetry_snapshot()
        normalized = snapshot.get("normalized") if isinstance(snapshot.get("normalized"), dict) else {}
        vendors = normalized.get("vendors") if isinstance(normalized, dict) else {}
        sampled_utc = str(snapshot.get("timestamp") or utc_now_iso())

        due: dict[str, list[dict[str, Any]]] = {s: [] for s in S2_SUBSTREAMS}
        for asset in self._assets(snapshot):
            vendor = _vendor_tag(asset, vendors or {})
            scope = _scope(asset)
            source_id = f"{vendor}_source"
            runtime_asset_id = str(asset.get("asset_id") or "unknown")
            for key, raw_point in (asset.get("telemetry") or {}).items():
                if not isinstance(raw_point, dict):
                    raw_point = {"value": raw_point, "quality": "unknown"}
                point = self.catalog.get(vendor, scope, str(key))
                if point and point.get("poll_enabled") is False:
                    continue
                if str(key) in S1_CRITICAL_KEYS:
                    continue
                substream = classify_substream(asset, str(key), point)
                if substream not in due:
                    continue
                policy, record_sec, upload_sec, signal_priority, retention, mode = policy_for(point)
                runtime_signal_id = f"{source_id}.{runtime_asset_id}.{key}"
                fp = fingerprint([raw_point.get("value"), raw_point.get("quality")])
                last_t = self._last_emit.get(runtime_signal_id)
                last_fp = self._last_fingerprint.get(runtime_signal_id)
                if last_t is None:
                    reason = "startup"
                elif mode == "change_or_heartbeat" and fp != last_fp:
                    reason = "change"
                elif now_mono - last_t >= record_sec:
                    reason = "heartbeat" if mode == "change_or_heartbeat" else "periodic"
                else:
                    continue

                point_id = str((point or {}).get("id") or f"{vendor}.{scope}.{key}")
                display_name = (point or {}).get("name_en") or raw_point.get("name") or str(key).replace("_", " ").title()
                category = (point or {}).get("category") or raw_point.get("category")
                unit = (point or {}).get("unit") or raw_point.get("unit")
                access = str((point or {}).get("access") or "R")
                record = {
                    "record_type": "general_asset_signal",
                    "sample_source": "gateway_runtime_cache",
                    "persisted_source": False,
                    "observed_at_utc": sampled_utc,
                    "source_updated_utc": asset.get("timestamp") or sampled_utc,
                    "snapshot_age_sec": None,
                    "source_data_age_ms": None,
                    "source_id": source_id,
                    "runtime_asset_id": runtime_asset_id,
                    "base_asset_id": str(asset.get("asset_type") or scope),
                    "substream": substream,
                    "runtime_signal_id": runtime_signal_id,
                    "point_id": point_id,
                    "signal": str(key),
                    "display_name": display_name,
                    "value": raw_point.get("value"),
                    "unit": unit,
                    "category": category,
                    "quality": raw_point.get("quality") or "unknown",
                    "policy": policy,
                    "central_record_sec": record_sec,
                    "upload_batch_sec": upload_sec,
                    "signal_priority": signal_priority,
                    "retention_class": retention,
                    "rw": access,
                    "key_signal": bool((point or {}).get("key_signal", False)),
                    "trigger_reason": reason,
                    # Additive dimensions; backend may ignore them.
                    "vendor": vendor,
                    "address_dec": (point or {}).get("address_dec"),
                    "address_hex": (point or {}).get("address_hex") or (point or {}).get("address"),
                    "read_fc": (point or {}).get("read_fc"),
                    "datatype": (point or {}).get("datatype"),
                }
                due[substream].append(record)
                self._last_emit[runtime_signal_id] = now_mono
                self._last_fingerprint[runtime_signal_id] = fp

        messages = []
        for substream in S2_SUBSTREAMS:
            records = due[substream]
            if not records:
                continue
            try:
                inserted, msg = await asyncio.to_thread(
                    emit_message,
                    config=self.config,
                    outbox=self.outbox,
                    stream=self.producer_config.stream,
                    substream=substream,
                    priority=self.producer_config.priority,
                    records=records,
                    created_at_utc=sampled_utc,
                )
            except OutboxCapacityError as exc:
                self.counters.failure_count += 1
                self.counters.last_error = str(exc)
                self._write_status()
                return {"emitted": bool(messages), "reason": "outbox_capacity", "messages": messages, "error": str(exc)}
            if inserted:
                messages.append({"substream": substream, "message_id": msg.message_id, "sequence": msg.sequence, "record_count": len(records)})
                self.counters.message_count += 1
                self.counters.record_count += len(records)
                self.counters.last_message_id = msg.message_id
                self.counters.last_sequence = msg.sequence

        self.counters.success_count += 1
        self.counters.last_success_utc = utc_now_iso()
        if messages:
            self.counters.last_enqueue_utc = utc_now_iso()
        self.counters.last_error = None
        self._write_status()
        return {"emitted": bool(messages), "message_count": len(messages), "messages": messages, "record_count": sum(m["record_count"] for m in messages)}

    @staticmethod
    def _assets(snapshot: dict[str, Any]) -> Iterable[dict[str, Any]]:
        seen: set[str] = set()
        candidates: list[Any] = []
        candidates.append(snapshot.get("bank"))
        if isinstance(snapshot.get("bms_banks"), dict):
            candidates.extend(snapshot["bms_banks"].values())
        candidates.extend(snapshot.get("racks") or [])
        if isinstance(snapshot.get("environment"), dict):
            candidates.extend(snapshot["environment"].values())
        if isinstance(snapshot.get("pcs_devices"), dict):
            candidates.extend(snapshot["pcs_devices"].values())
        elif snapshot.get("pcs"):
            candidates.append(snapshot.get("pcs"))
        for asset in candidates:
            if not isinstance(asset, dict):
                continue
            aid = str(asset.get("asset_id") or "")
            if aid and aid in seen:
                continue
            if aid:
                seen.add(aid)
            yield asset
