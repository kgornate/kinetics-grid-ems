from __future__ import annotations

import asyncio
import time
from typing import Any

from .config import CentralSyncConfig
from .contracts import utc_now_iso
from .local_gateway_api import LocalGatewayApiClient
from .outbox import OutboxStore
from .producer_common import ProducerCounters, ProducerLoopMixin, emit_message, fingerprint


class ChargeDischargeProducer(ProducerLoopMixin):
    """S10 application stream for vendor-neutral PairController runtime."""

    def __init__(self, *, config: CentralSyncConfig, outbox: OutboxStore, local_api: Any | None = None) -> None:
        self.config = config
        self.producer_config = config.charge_discharge
        self.outbox = outbox
        self.local_api = local_api or LocalGatewayApiClient(config.local_gateway_api)
        self._owns_api = local_api is None
        self.counters = ProducerCounters()
        self.running = False
        self.started_utc = utc_now_iso()
        self._stop = asyncio.Event()
        self._last_fp: str | None = None
        self._last_emit_mono = 0.0

    async def close(self) -> None:
        if self._owns_api:
            await self.local_api.close()

    async def collect_once(self, *, force_emit: bool = False) -> dict[str, Any]:
        self.counters.poll_count += 1
        self.counters.last_poll_utc = utc_now_iso()
        status = await self.local_api.control_status_compact()
        readiness = await self.local_api.platform_readiness()
        now = str(status.get("timestamp") or utc_now_iso())
        pairs_raw = status.get("pairs") or {}
        if isinstance(pairs_raw, list):
            pairs = {str(x.get("pair_id")): x for x in pairs_raw if isinstance(x, dict) and x.get("pair_id")}
        elif isinstance(pairs_raw, dict):
            pairs = pairs_raw
        else:
            pairs = {}
        summary = status.get("summary") or {}
        records = []
        for pair_id, pair in sorted(pairs.items()):
            if not isinstance(pair, dict): continue
            records.append({
                "timestamp_utc": now,
                "application": "battery_charge_discharge_control",
                "application_version": "1.0",
                "available": True,
                "pair_id": pair_id,
                "stage": pair.get("stage"),
                "run_status": pair.get("run_status"),
                "direction": pair.get("direction"),
                "requested_power_kw": pair.get("requested_power_kw"),
                "commanded_power_kw": pair.get("commanded_power_kw"),
                "actual_power_kw": pair.get("pcs_actual_power_kw"),
                "rack_voltage_v": pair.get("rack_voltage_v"),
                "rack_soc_percent": pair.get("rack_soc_percent"),
                "battery_ready": pair.get("battery_ready"),
                "pcs_running": pair.get("pcs_running"),
                "hard_blocked": pair.get("hard_blocked"),
                "errors": pair.get("errors") or [],
                "parallel_operation_supported": summary.get("parallel_operation_supported"),
                "active_pairs": summary.get("active_pairs") or [],
                "starting_pairs": summary.get("starting_pairs") or [],
                "startup_policy": summary.get("startup_policy"),
                "platform_ready": readiness.get("ready") if isinstance(readiness, dict) else None,
                "commissioning_status": readiness.get("commissioning") if isinstance(readiness, dict) else None,
                "command_transport": "D1 command_requests",
                "result_stream": "S9 command_results",
                "raw_modbus_write_bypass": False,
            })
        if not records:
            records = [{
                "timestamp_utc": now, "application": "battery_charge_discharge_control",
                "application_version": "1.0", "available": True, "pair_id": None,
                "stage": None, "run_status": "no_enabled_pairs", "direction": None,
                "requested_power_kw": None, "commanded_power_kw": None, "actual_power_kw": None,
                "rack_voltage_v": None, "rack_soc_percent": None, "battery_ready": None,
                "pcs_running": None, "hard_blocked": True, "errors": ["no_enabled_pairs"],
                "parallel_operation_supported": summary.get("parallel_operation_supported"),
                "active_pairs": summary.get("active_pairs") or [], "starting_pairs": summary.get("starting_pairs") or [],
                "startup_policy": summary.get("startup_policy"), "platform_ready": readiness.get("ready") if isinstance(readiness, dict) else None,
                "commissioning_status": readiness.get("commissioning") if isinstance(readiness, dict) else None,
                "command_transport": "D1 command_requests", "result_stream": "S9 command_results", "raw_modbus_write_bypass": False,
            }]
        fp = fingerprint([{k:v for k,v in r.items() if k != "timestamp_utc"} for r in records])
        changed = self._last_fp is not None and fp != self._last_fp
        due = force_emit or self._last_fp is None or changed or (time.monotonic() - self._last_emit_mono >= self.producer_config.heartbeat_interval_sec)
        if not due:
            return {"emitted": False, "reason": "not_due"}
        inserted, msg = await asyncio.to_thread(
            emit_message, config=self.config, outbox=self.outbox,
            stream=self.producer_config.stream, substream=self.producer_config.substream,
            priority=self.producer_config.priority, records=records, created_at_utc=now,
        )
        self._last_fp = fp
        self._last_emit_mono = time.monotonic()
        self.counters.success_count += 1
        self.counters.last_success_utc = utc_now_iso()
        if inserted:
            self.counters.message_count += 1
            self.counters.record_count += len(records)
            self.counters.last_enqueue_utc = utc_now_iso()
            self.counters.last_message_id = msg.message_id
            self.counters.last_sequence = msg.sequence
        self.counters.last_error = None
        self._write_status()
        return {"emitted": bool(inserted), "record_count": len(records), "message_id": msg.message_id if msg else None, "transition": changed}
