from __future__ import annotations

import asyncio
import time
from typing import Any

from .config import CentralSyncConfig
from .contracts import utc_now_iso
from .local_gateway_api import LocalGatewayApiClient
from .outbox import OutboxCapacityError, OutboxStore
from .producer_common import ProducerCounters, ProducerLoopMixin, emit_message, parse_iso_epoch_ms


PCS_KEYS = (
    "running", "charging", "discharging", "faulted", "standby", "shutdown", "epo",
    "off_grid", "dc_precharge_connected", "dc_relay_connected", "ac_relay_connected",
    "active_power_kw", "reactive_power_kvar", "power_factor", "dc_voltage_v",
    "dc_current_a", "dc_power_kw", "dc_bus_voltage_v", "grid_frequency_hz",
    "grid_voltage_ab_v", "grid_voltage_bc_v", "grid_voltage_ca_v", "raw_status",
)
BMS_KEYS = (
    "state", "state_code", "voltage_v", "current_a", "soc_percent", "soh_percent",
    "max_charge_power_kw", "max_discharge_power_kw", "max_charge_current_a",
    "max_discharge_current_a", "positive_contactor_closed", "negative_contactor_closed",
    "positive_insulation_mohm", "negative_insulation_mohm", "max_cell_voltage_v",
    "min_cell_voltage_v", "max_cell_temperature_c", "min_cell_temperature_c",
    "charge_allowed", "discharge_allowed", "blocking_reasons",
)


def _signal(value: Any, *, updated_utc: str | None = None, unit: str | None = None) -> dict[str, Any]:
    quality = "good" if value is not None else "missing"
    return {
        "value": value,
        "unit": unit,
        "quality": quality,
        "category": "normalized_fast",
        "display_name": None,
        "updated_utc": updated_utc,
        "age_ms": None,
    }


class FastBESSProducer(ProducerLoopMixin):
    """S1 producer with the same per-BESS record shape as Northbound."""

    def __init__(self, *, config: CentralSyncConfig, outbox: OutboxStore, local_api: Any | None = None) -> None:
        self.config = config
        self.producer_config = config.fast_bess
        self.outbox = outbox
        self.local_api = local_api or LocalGatewayApiClient(config.local_gateway_api)
        self._owns_api = local_api is None
        self.counters = ProducerCounters()
        self.running = False
        self.started_utc = utc_now_iso()
        self._stop = asyncio.Event()
        self._last_sequence: Any = object()

    async def close(self) -> None:
        if self._owns_api:
            await self.local_api.close()

    async def collect_once(self) -> dict[str, Any]:
        self.counters.poll_count += 1
        self.counters.last_poll_utc = utc_now_iso()
        normalized = await self.local_api.normalized_snapshot()
        source_sequence = normalized.get("sequence")
        source_ts = str(normalized.get("timestamp") or utc_now_iso())
        if source_sequence == self._last_sequence:
            return {"emitted": False, "reason": "duplicate_snapshot"}

        pairs = normalized.get("pairs") or {}
        records: list[dict[str, Any]] = []
        iterable = pairs.items() if isinstance(pairs, dict) else []
        for index, (pair_id, pair) in enumerate(iterable, start=1):
            if not isinstance(pair, dict) or not pair.get("enabled", True):
                continue
            battery = pair.get("battery") or {}
            pcs = pair.get("pcs") or {}
            pcs_updated = pcs.get("timestamp") or source_ts
            bms_updated = battery.get("timestamp") or source_ts
            pcs_values = {key: _signal(pcs.get(key), updated_utc=pcs_updated) for key in PCS_KEYS}
            bms_values = {key: _signal(battery.get(key), updated_utc=bms_updated) for key in BMS_KEYS}
            pcs_good = sum(1 for v in pcs_values.values() if v["quality"] == "good")
            bms_good = sum(1 for v in bms_values.values() if v["quality"] == "good")
            selected = len(pcs_values) + len(bms_values)
            good = pcs_good + bms_good
            bad = selected - good
            if bad == 0:
                quality = "good"
            elif good:
                quality = "partial"
            else:
                quality = "bad"
            ts_ms = parse_iso_epoch_ms(source_ts) or int(time.time() * 1000)
            record = {
                "schema_version": 1,
                "record_type": "fast_bess_sample",
                "sample_source": "gateway_runtime_cache",
                "persisted_source": False,
                "timestamp_utc": source_ts,
                "timestamp_epoch_ms": ts_ms,
                "source_id": str(pair_id),
                "bess_id": f"bess_{index}",
                "pcs_asset_id": pair.get("pcs_asset_id") or pcs.get("asset_id"),
                "bms_asset_id": battery.get("asset_id") or f"bms_rack_{pair.get('rack_id') or index}",
                "profile_name": "kalpa_lineage_elecod_fast_v1",
                "pcs_values": pcs_values,
                "bms_values": bms_values,
                "pcs_signal_count": len(pcs_values),
                "bms_signal_count": len(bms_values),
                "selected_signal_count": selected,
                "good_signal_count": good,
                "bad_signal_count": bad,
                "pcs_good_signal_count": pcs_good,
                "pcs_bad_signal_count": len(pcs_values) - pcs_good,
                "bms_good_signal_count": bms_good,
                "bms_bad_signal_count": len(bms_values) - bms_good,
                "max_data_age_ms": None,
                "quality": quality,
                "pcs_last_update_utc": pcs_updated,
                "bms_last_update_utc": bms_updated,
                "snapshot_age_sec": None,
            }
            records.append(record)

        if not records:
            self.counters.failure_count += 1
            self.counters.last_error = "normalized snapshot has no enabled pairs"
            self._write_status()
            return {"emitted": False, "reason": "no_pairs"}

        try:
            inserted, message = await asyncio.to_thread(
                emit_message,
                config=self.config,
                outbox=self.outbox,
                stream=self.producer_config.stream,
                substream=self.producer_config.substream,
                priority=self.producer_config.priority,
                records=records,
                created_at_utc=source_ts,
            )
        except OutboxCapacityError as exc:
            self.counters.failure_count += 1
            self.counters.last_error = str(exc)
            self._write_status()
            return {"emitted": False, "reason": "outbox_capacity", "error": str(exc)}
        self._last_sequence = source_sequence
        self.counters.success_count += 1
        if inserted:
            self.counters.message_count += 1
            self.counters.record_count += len(records)
            self.counters.last_enqueue_utc = utc_now_iso()
            self.counters.last_message_id = message.message_id
            self.counters.last_sequence = message.sequence
        self.counters.last_success_utc = utc_now_iso()
        self.counters.last_error = None
        self._write_status()
        return {"emitted": bool(inserted), "record_count": len(records), "message_id": getattr(message, "message_id", None)}
