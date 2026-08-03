from __future__ import annotations

import json
import logging
import threading
import time
import zlib
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.assets.bms_driver import BmsModbusDriver
from app.assets.mock_plant import MockPlant, SCENARIOS
from app.assets.pcs_driver import PcsModbusDriver
from app.core.catalog import ProtocolCatalog, apply_pcs_overrides
from app.core.config import GatewayConfig, resolve_path
from app.services.alarm_engine import AlarmEngine
from app.services.bms_pcs_control import BmsPcsControlService
from app.protocols.planner import build_read_blocks
from app.storage.sqlite_store import SQLiteStore

LOGGER = logging.getLogger(__name__)
POLL_CLASSES = ("fast", "normal", "slow", "bulk")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GatewayService:
    """Owns the complete cached plant state and independently polls each data-rate class."""

    def __init__(self, config: GatewayConfig, store: SQLiteStore) -> None:
        self.config = config
        self.store = store
        self.bms_catalog = ProtocolCatalog.load(resolve_path(config.bms_catalog_file))
        pcs_catalog = ProtocolCatalog.load(resolve_path(config.pcs_catalog_file))
        self.pcs_catalog = apply_pcs_overrides(pcs_catalog, resolve_path(config.pcs.overrides_file))
        self.mock = MockPlant(self.bms_catalog, self.pcs_catalog, len(config.bms.racks), config.mock.seed)
        self.mock.set_scenario(config.mock.scenario)
        self.bms_driver = BmsModbusDriver(config.bms, self.bms_catalog)
        self.pcs_driver = PcsModbusDriver(config.pcs, self.pcs_catalog)
        self.control_sequence = BmsPcsControlService(
            config,
            self.bms_driver,
            self.pcs_driver,
            store,
            snapshot_provider=self.control_pair_snapshot,
        )
        self.alarm_engine = AlarmEngine()
        self._lock = threading.RLock()
        self._snapshot: dict[str, Any] = self._empty_snapshot()
        self._sequence = 0
        self._updates: deque[dict[str, Any]] = deque(
            maxlen=self.config.storage.update_buffer_events
        )
        self._last_store_at = 0.0
        self._last_storage_status_at = 0.0
        self._storage_status_cache = self.store.status()
        self._active_alarm_cache = {
            alarm["alarm_key"]: alarm
            for alarm in self.store.list_alarms(active_only=True, limit=5000)
        }
        self._last_poll_error: str | None = None
        self._poll_stats: dict[str, dict[str, Any]] = {
            name: {
                "count": 0,
                "errors": 0,
                "last_started_at": None,
                "last_completed_at": None,
                "last_duration_ms": None,
                "last_event_bytes": 0,
                "total_event_bytes": 0,
            }
            for name in (*POLL_CLASSES, "pcs")
        }
        self._storage_sample_stats = {
            "samples": 0,
            "last_uncompressed_bytes": 0,
            "last_stored_bytes": 0,
            "total_uncompressed_bytes": 0,
            "total_stored_bytes": 0,
        }
        self._initializing = True
        self.refresh_all()
        self._initializing = False
        self._store_snapshot_if_due(self._snapshot, force=True)

    def _empty_snapshot(self) -> dict[str, Any]:
        racks = [
            {
                "asset_id": f"bms_rack_{rack.rack_id}",
                "asset_type": "bms_rack",
                "rack_id": rack.rack_id,
                "online": False,
                "timestamp": None,
                "telemetry": {},
                "poll_status": {},
            }
            for rack in self.config.bms.racks
        ]
        return {
            "gateway_id": self.config.gateway_id,
            "mode": self.config.mode,
            "sequence": 0,
            "timestamp": now_iso(),
            "bank": {
                "asset_id": "bms_bank",
                "asset_type": "bms_bank",
                "online": False,
                "timestamp": None,
                "telemetry": {},
                "poll_status": {},
            },
            "bms_banks": {
                f"bms_bank_{rack.rack_id}": {
                    "asset_id": f"bms_bank_{rack.rack_id}",
                    "asset_type": "bms_bank",
                    "rack_id": rack.rack_id,
                    "online": False,
                    "timestamp": None,
                    "telemetry": {},
                    "poll_status": {},
                }
                for rack in self.config.bms.racks
            },
            "racks": racks,
            "environment": {},
            # Keep the original singular `pcs` object for the existing Flutter/API
            # clients. `pcs_devices` is the new multi-PCS collection.
            "pcs": {
                "asset_id": self.config.pcs.primary_device.asset_id,
                "asset_type": "pcs",
                "online": False,
                "timestamp": None,
                "telemetry": {},
                "poll_status": {},
            },
            "pcs_devices": {
                device.asset_id: {
                    "asset_id": device.asset_id,
                    "asset_type": "pcs",
                    "label": device.label,
                    "unit_id": device.unit_id,
                    "online": False,
                    "disabled": (not self.config.pcs.enabled) or (not device.enabled),
                    "timestamp": None,
                    "telemetry": {},
                    "poll_status": {},
                }
                for device in self.config.pcs.devices
            },
            "alarms": [],
            "polling": {},
            "storage": {},
        }

    @property
    def scenarios(self) -> list[str]:
        return sorted(SCENARIOS)

    def refresh_all(self) -> dict[str, Any]:
        for poll_class in POLL_CLASSES:
            self.poll_bms_class(poll_class)
        self.poll_pcs()
        return self.snapshot()

    def refresh(self, *, include_slow: bool = False, include_bulk: bool | None = None) -> dict[str, Any]:
        """Compatibility refresh used by REST. Background scheduling uses poll_bms_class/poll_pcs."""
        self.poll_bms_class("fast")
        self.poll_bms_class("normal")
        if include_slow:
            self.poll_bms_class("slow")
        bulk = self.config.bms.include_bulk_in_live_snapshot if include_bulk is None else include_bulk
        if bulk:
            self.poll_bms_class("bulk")
        self.poll_pcs()
        return self.snapshot()

    def poll_bms_class(self, poll_class: str) -> dict[str, Any]:
        if poll_class not in POLL_CLASSES:
            raise ValueError(f"Unsupported BMS poll class: {poll_class}")
        started = time.perf_counter()
        started_at = now_iso()
        error_text: str | None = None
        try:
            updates = self._mock_bms_class(poll_class) if self.config.mode == "mock" else self._hardware_bms_class(poll_class)
        except Exception as error:
            error_text = str(error)
            LOGGER.exception("BMS %s poll failed", poll_class)
            if self.config.mode == "mixed":
                updates = self._mock_bms_class(poll_class)
                for asset in updates:
                    asset["source"] = "mock_fallback"
                    asset["hardware_error"] = error_text
            else:
                updates = []
        duration_ms = (time.perf_counter() - started) * 1000
        with self._lock:
            for asset in updates:
                self._merge_asset(asset, poll_class)
            event = self._finalize_poll(poll_class, updates, started_at, duration_ms, error_text)
            return deepcopy(event)

    def poll_pcs(self) -> dict[str, Any]:
        """Poll all configured PCS slaves sequentially on the shared transport."""
        started = time.perf_counter()
        started_at = now_iso()
        updates: list[dict[str, Any]] = []
        errors: list[str] = []
        mock_primary = None
        if self.config.mode in {"mock", "mixed"}:
            mock_primary = self.mock.snapshot(include_slow=True, include_bulk=True)["pcs"]

        for device in self.config.pcs.devices:
            try:
                if not self.config.pcs.enabled or not device.enabled:
                    update = self.pcs_driver.disabled_asset(device)
                elif self.config.mode == "mock":
                    update = deepcopy(mock_primary)
                    update["asset_id"] = device.asset_id
                    update["label"] = device.label
                    update["unit_id"] = device.unit_id
                    update["transport"] = self.config.pcs.transport
                else:
                    update = self.pcs_driver.read_all(device.asset_id)
            except Exception as error:
                error_text = f"{device.asset_id}: {error}"
                errors.append(error_text)
                LOGGER.exception("PCS poll failed asset=%s", device.asset_id)
                if self.config.mode == "mixed" and mock_primary is not None:
                    update = deepcopy(mock_primary)
                    update["asset_id"] = device.asset_id
                    update["label"] = device.label
                    update["unit_id"] = device.unit_id
                    update["transport"] = self.config.pcs.transport
                    update["source"] = "mock_fallback"
                    update["hardware_error"] = str(error)
                else:
                    update = {
                        "asset_id": device.asset_id,
                        "asset_type": "pcs",
                        "label": device.label,
                        "unit_id": device.unit_id,
                        "transport": self.config.pcs.transport,
                        "online": False,
                        "timestamp": now_iso(),
                        "telemetry": {},
                        "read_errors": [{"error": str(error)}],
                    }
            updates.append(update)

        duration_ms = (time.perf_counter() - started) * 1000
        error_text = "; ".join(errors) if errors else None
        with self._lock:
            for update in updates:
                self._merge_asset(update, "pcs")
            return deepcopy(
                self._finalize_poll("pcs", updates, started_at, duration_ms, error_text)
            )

    def _hardware_bms_class(self, poll_class: str) -> list[dict[str, Any]]:
        updates: list[dict[str, Any]] = []
        for rack in self.config.bms.racks:
            updates.append(
                self.bms_driver.read_asset_classes(
                    f"bms_bank_{rack.rack_id}", {poll_class}
                )
            )
            updates.append(
                self.bms_driver.read_asset_classes(
                    f"bms_rack_{rack.rack_id}", {poll_class}
                )
            )
        env_raw = self.bms_driver.read_asset_classes("bms_environment", {poll_class})
        updates.extend(self._split_environment_asset(env_raw))
        return updates

    def _mock_bms_class(self, poll_class: str) -> list[dict[str, Any]]:
        full = self.mock.snapshot(include_slow=True, include_bulk=True)
        updates: list[dict[str, Any]] = []
        bank_keys = self._keys_for("bank", poll_class)
        rack_keys = self._keys_for("rack", poll_class)
        env_keys = self._keys_for("environment", poll_class)
        if bank_keys:
            for rack in self.config.bms.racks:
                bank = self._filter_asset(full["bank"], bank_keys)
                bank["asset_id"] = f"bms_bank_{rack.rack_id}"
                bank["rack_id"] = rack.rack_id
                updates.append(bank)
        if rack_keys:
            updates.extend(self._filter_asset(rack, rack_keys) for rack in full["racks"])
        if env_keys:
            for asset in full["environment"].values():
                filtered = self._filter_asset(asset, env_keys)
                if filtered["telemetry"]:
                    updates.append(filtered)
        return updates

    def _keys_for(self, scope: str, poll_class: str) -> set[str]:
        return {
            str(point["key"])
            for point in self.bms_catalog.select(
                scope=scope, poll_classes={poll_class}, include_reserved=False
            )
        }

    @staticmethod
    def _filter_asset(asset: dict[str, Any], keys: set[str]) -> dict[str, Any]:
        result = {key: deepcopy(value) for key, value in asset.items() if key != "telemetry"}
        result["telemetry"] = {
            key: deepcopy(value) for key, value in asset.get("telemetry", {}).items() if key in keys
        }
        return result

    def _split_environment_asset(self, env_raw: dict[str, Any]) -> list[dict[str, Any]]:
        env_groups = self.mock._split_environment(env_raw.get("telemetry", {}))
        return [
            {
                "asset_id": key,
                "asset_type": key,
                "online": env_raw.get("online", False),
                "timestamp": env_raw.get("timestamp"),
                "telemetry": points,
                "source_endpoint": {
                    "host": env_raw.get("host"),
                    "port": env_raw.get("port"),
                    "unit_id": env_raw.get("unit_id"),
                },
                "read_errors": env_raw.get("read_errors", []),
            }
            for key, points in env_groups.items()
            if points
        ]

    def _asset_location(self, asset_id: str) -> tuple[str, int | str | None]:
        if asset_id == "bms_bank":
            return "bank", None
        if asset_id.startswith("bms_bank_"):
            return "bms_banks", asset_id
        if asset_id in self._snapshot.get("pcs_devices", {}):
            return "pcs_devices", asset_id
        if asset_id.startswith("bms_rack_"):
            return "racks", int(asset_id.rsplit("_", 1)[1])
        return "environment", asset_id

    def _merge_asset(self, update: dict[str, Any], poll_class: str) -> None:
        asset_id = str(update["asset_id"])
        location, selector = self._asset_location(asset_id)
        if location == "bank":
            current = self._snapshot["bank"]
        elif location == "bms_banks":
            current = self._snapshot["bms_banks"].setdefault(
                str(selector),
                {
                    "asset_id": asset_id,
                    "asset_type": "bms_bank",
                    "online": False,
                    "timestamp": None,
                    "telemetry": {},
                    "poll_status": {},
                },
            )
        elif location == "pcs_devices":
            current = self._snapshot["pcs_devices"].setdefault(
                str(selector),
                {
                    "asset_id": asset_id,
                    "asset_type": "pcs",
                    "online": False,
                    "timestamp": None,
                    "telemetry": {},
                    "poll_status": {},
                },
            )
        elif location == "racks":
            current = next(r for r in self._snapshot["racks"] if int(r["rack_id"]) == selector)
        else:
            current = self._snapshot["environment"].setdefault(
                str(selector),
                {
                    "asset_id": asset_id,
                    "asset_type": update.get("asset_type", asset_id),
                    "online": False,
                    "timestamp": None,
                    "telemetry": {},
                    "poll_status": {},
                },
            )
        current.setdefault("telemetry", {}).update(deepcopy(update.get("telemetry", {})))
        for key, value in update.items():
            if key not in {"telemetry", "poll_status"}:
                current[key] = deepcopy(value)
        current.setdefault("poll_status", {})[poll_class] = {
            "timestamp": update.get("timestamp") or now_iso(),
            "online": bool(update.get("online", False)),
            "read_errors": deepcopy(update.get("read_errors", [])),
            "point_count": len(update.get("telemetry", {})),
        }
        if poll_class in {"fast", "normal", "pcs"} or current.get("timestamp") is None:
            current["online"] = bool(update.get("online", False))
        current["timestamp"] = update.get("timestamp") or now_iso()
        if location == "pcs_devices" and asset_id == self.config.pcs.primary_device.asset_id:
            self._snapshot["pcs"] = deepcopy(current)
        if location == "bms_banks" and asset_id == "bms_bank_1":
            legacy = deepcopy(current)
            legacy["asset_id"] = "bms_bank"
            self._snapshot["bank"] = legacy

    def _storage_status(self, *, force: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if (
            force
            or not self._storage_status_cache
            or now - self._last_storage_status_at >= self.config.storage.status_refresh_seconds
        ):
            self._storage_status_cache = self.store.status()
            self._last_storage_status_at = now
        return deepcopy(self._storage_status_cache)

    def _finalize_poll(
        self,
        poll_class: str,
        updates: list[dict[str, Any]],
        started_at: str,
        duration_ms: float,
        error_text: str | None,
    ) -> dict[str, Any]:
        self._sequence += 1
        timestamp = now_iso()
        self._snapshot["gateway_id"] = self.config.gateway_id
        self._snapshot["mode"] = self.config.mode
        self._snapshot["sequence"] = self._sequence
        self._snapshot["timestamp"] = timestamp
        self._snapshot["alarms"] = self._update_alarms(self._snapshot)
        self._snapshot["storage"] = self._storage_status()
        self._last_poll_error = error_text
        event = {
            "type": "telemetry_update",
            "sequence": self._sequence,
            "gateway_id": self.config.gateway_id,
            "timestamp": timestamp,
            "poll_class": poll_class,
            "assets": [self._compact_asset(asset) for asset in updates],
        }
        event_bytes = len(json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        stats = self._poll_stats[poll_class]
        stats["count"] += 1
        stats["errors"] += 1 if error_text else 0
        stats["last_started_at"] = started_at
        stats["last_completed_at"] = timestamp
        stats["last_duration_ms"] = round(duration_ms, 3)
        stats["last_event_bytes"] = event_bytes
        stats["total_event_bytes"] += event_bytes
        stats["average_event_bytes"] = round(stats["total_event_bytes"] / stats["count"], 2)
        self._snapshot["polling"] = deepcopy(self._poll_stats)
        self._updates.append(event)
        if not self._initializing:
            self._store_snapshot_if_due(self._snapshot)
        return event

    def control_pair_snapshot(self, rack_id: int, pcs_asset_id: str) -> dict[str, Any]:
        """Return only the cached assets required by runtime safety monitoring.

        This avoids deep-copying the complete plant snapshot for every active
        pair every two seconds while preserving a consistent view under the
        gateway cache lock.
        """
        with self._lock:
            rack = next(
                (
                    item
                    for item in self._snapshot.get("racks", [])
                    if int(item.get("rack_id") or 0) == int(rack_id)
                ),
                None,
            )
            pcs = self._snapshot.get("pcs_devices", {}).get(pcs_asset_id)
            if rack is None:
                raise KeyError(f"Cached BMS rack {rack_id} is unavailable")
            if pcs is None:
                raise KeyError(f"Cached PCS asset {pcs_asset_id} is unavailable")
            return {
                "gateway_id": self.config.gateway_id,
                "sequence": self._sequence,
                "timestamp": self._snapshot.get("timestamp"),
                "bank": deepcopy(
                    self._snapshot.get("bms_banks", {}).get(
                        f"bms_bank_{rack_id}", self._snapshot.get("bank", {})
                    )
                ),
                "rack": deepcopy(rack),
                "pcs": deepcopy(pcs),
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._snapshot)

    def compact_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "type": "snapshot",
                "sequence": self._sequence,
                "gateway_id": self.config.gateway_id,
                "mode": self.config.mode,
                "timestamp": self._snapshot.get("timestamp"),
                "bank": self._compact_asset(self._snapshot["bank"]),
                "bms_banks": {
                    asset_id: self._compact_asset(asset)
                    for asset_id, asset in self._snapshot.get("bms_banks", {}).items()
                },
                "racks": [self._compact_asset(rack) for rack in self._snapshot["racks"]],
                "environment": {
                    key: self._compact_asset(asset)
                    for key, asset in self._snapshot["environment"].items()
                },
                "pcs": self._compact_asset(self._snapshot["pcs"]),
                "pcs_devices": {
                    asset_id: self._compact_asset(asset)
                    for asset_id, asset in self._snapshot.get("pcs_devices", {}).items()
                },
                "alarms": deepcopy(self._snapshot.get("alarms", [])),
            }

    @staticmethod
    def _compact_point(point: Any) -> Any:
        if not isinstance(point, dict):
            return point
        result: dict[str, Any] = {
            "v": deepcopy(point.get("value")),
            "q": point.get("quality", "unknown"),
        }
        raw = point.get("raw")
        if raw is not None and raw != point.get("value"):
            result["r"] = deepcopy(raw)
        if point.get("unit"):
            result["u"] = point.get("unit")
        if point.get("bitfields"):
            result["b"] = deepcopy(point.get("bitfields"))
        return result

    def _compact_asset(self, asset: dict[str, Any]) -> dict[str, Any]:
        return {
            "asset_id": asset.get("asset_id"),
            "asset_type": asset.get("asset_type"),
            "rack_id": asset.get("rack_id"),
            "label": asset.get("label"),
            "unit_id": asset.get("unit_id"),
            "transport": asset.get("transport"),
            "disabled": asset.get("disabled", False),
            "online": asset.get("online"),
            "timestamp": asset.get("timestamp"),
            "telemetry": {
                key: self._compact_point(value) for key, value in asset.get("telemetry", {}).items()
            },
        }

    def updates_since(self, sequence: int) -> list[dict[str, Any]]:
        with self._lock:
            return [deepcopy(event) for event in self._updates if int(event["sequence"]) > sequence]

    def rack_details(self, rack_id: int) -> dict[str, Any]:
        if rack_id not in {rack.rack_id for rack in self.config.bms.racks}:
            raise KeyError(f"Rack {rack_id} is not configured")
        with self._lock:
            rack = next(r for r in self._snapshot["racks"] if int(r["rack_id"]) == rack_id)
            return deepcopy(rack)

    def _all_assets(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        pcs_assets = list(snapshot.get("pcs_devices", {}).values())
        if not pcs_assets and isinstance(snapshot.get("pcs"), dict):
            pcs_assets = [snapshot["pcs"]]
        bank_assets: list[dict[str, Any]] = []
        if isinstance(snapshot.get("bank"), dict):
            bank_assets.append(snapshot["bank"])
        bank_assets.extend(
            asset
            for asset_id, asset in snapshot.get("bms_banks", {}).items()
            if asset_id != "bms_bank_1"
        )
        assets = [*bank_assets, *snapshot["racks"], *snapshot["environment"].values(), *pcs_assets]
        return [asset for asset in assets if isinstance(asset, dict)]

    def _update_alarms(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        current: dict[str, dict[str, Any]] = {}
        for asset in self._all_assets(snapshot):
            if asset.get("disabled"):
                continue
            for alarm in self.alarm_engine.extract(asset):
                key = alarm["alarm_key"]
                previous = self._active_alarm_cache.get(key)
                if previous:
                    alarm["raised_at"] = previous.get("raised_at") or alarm.get("raised_at")
                current[key] = alarm

        def comparable(alarm: dict[str, Any]) -> dict[str, Any]:
            return {
                "alarm_key": alarm.get("alarm_key"),
                "asset_id": alarm.get("asset_id"),
                "code": alarm.get("code"),
                "severity": alarm.get("severity"),
                "active": bool(alarm.get("active", True)),
                "message": alarm.get("message"),
                "payload": alarm.get("payload") or {},
            }

        for key, alarm in current.items():
            previous = self._active_alarm_cache.get(key)
            if previous is None or comparable(previous) != comparable(alarm):
                self.store.upsert_alarm(alarm)

        for key, alarm in self._active_alarm_cache.items():
            if key not in current:
                cleared = dict(alarm)
                cleared["active"] = False
                cleared["cleared_at"] = now_iso()
                self.store.upsert_alarm(cleared)

        self._active_alarm_cache = deepcopy(current)
        return list(current.values())

    def _history_asset(self, asset: dict[str, Any]) -> dict[str, Any]:
        if not self.config.storage.compact_history:
            return {
                "online": asset.get("online"),
                "timestamp": asset.get("timestamp"),
                "telemetry": deepcopy(asset.get("telemetry", {})),
            }
        telemetry: dict[str, Any] = {}
        for key, point in asset.get("telemetry", {}).items():
            compact = self._compact_point(point)
            if not self.config.storage.store_raw_when_distinct:
                compact.pop("r", None)
            telemetry[key] = compact
        return {
            "online": asset.get("online"),
            "timestamp": asset.get("timestamp"),
            "telemetry": telemetry,
        }

    def _store_snapshot_if_due(self, snapshot: dict[str, Any], *, force: bool = False) -> None:
        now = time.monotonic()
        interval = self.store.sample_interval_seconds
        if not force and now - self._last_store_at < interval:
            return
        self._last_store_at = now

        timestamp = snapshot.get("timestamp")
        samples = [
            (
                str(asset.get("asset_id", "unknown")),
                self._history_asset(asset),
                timestamp,
            )
            for asset in self._all_assets(snapshot)
        ]
        sizes = self.store.store_telemetry_batch(samples)
        raw_total = sizes["uncompressed_bytes"]
        stored_total = sizes["stored_bytes"]

        stats = self._storage_sample_stats
        stats["samples"] += 1
        stats["last_uncompressed_bytes"] = raw_total
        stats["last_stored_bytes"] = stored_total
        stats["total_uncompressed_bytes"] += raw_total
        stats["total_stored_bytes"] += stored_total
        stats["average_uncompressed_bytes"] = round(
            stats["total_uncompressed_bytes"] / stats["samples"], 2
        )
        stats["average_stored_bytes"] = round(
            stats["total_stored_bytes"] / stats["samples"], 2
        )

    def set_mock_scenario(self, scenario: str) -> dict[str, Any]:
        with self._lock:
            self.mock.set_scenario(scenario)
            self.config.mock.scenario = scenario
        return {"ok": True, "scenario": scenario, "snapshot": self.refresh_all()}

    def execute_control(self, username: str, asset_id: str, point_key: str, value: Any) -> dict[str, Any]:
        try:
            if asset_id in {device.asset_id for device in self.config.pcs.devices}:
                if self.config.mode == "mock":
                    point = self.pcs_catalog.by_key(point_key, scope="pcs")
                    if not point:
                        raise KeyError(point_key)
                    response = self.mock.write("pcs_1", point, value)
                    response["asset_id"] = asset_id
                else:
                    response = self.pcs_driver.write_point(asset_id, point_key, value)
            else:
                endpoint_scope = (
                    "bank"
                    if asset_id == "bms_bank" or asset_id.startswith("bms_bank_")
                    else ("rack" if asset_id.startswith("bms_rack_") else "environment")
                )
                point = self.bms_catalog.by_key(point_key, scope=endpoint_scope)
                if not point:
                    raise KeyError(point_key)
                if "W" not in str(point.get("access", "R")).upper():
                    raise PermissionError(f"Point {point_key} is read-only")
                if self.config.mode == "mock":
                    response = self.mock.write(asset_id, point, value)
                else:
                    bms_asset_id = "bms_environment" if endpoint_scope == "environment" else asset_id
                    response = self.bms_driver.write_point(bms_asset_id, point_key, value)
            self.store.audit_command(username, asset_id, point_key, value, "success", response)
            self.store.event("command", f"Command {point_key} executed", asset_id=asset_id, payload=response)
            return response
        except Exception as error:
            response = {"ok": False, "error": str(error), "asset_id": asset_id, "point_key": point_key}
            self.store.audit_command(username, asset_id, point_key, value, "failed", response)
            raise

    def pcs_details(self, asset_id: str) -> dict[str, Any]:
        with self._lock:
            devices = self._snapshot.get("pcs_devices", {})
            if asset_id not in devices:
                raise KeyError(f"PCS asset {asset_id} is not configured")
            return deepcopy(devices[asset_id])

    def assets(self) -> list[dict[str, Any]]:
        snapshot = self.snapshot()
        return [
            {
                "asset_id": asset.get("asset_id"),
                "asset_type": asset.get("asset_type"),
                "enabled": not bool(asset.get("disabled", False)),
                "online": asset.get("online"),
                "telemetry_point_count": len(asset.get("telemetry", {})),
                "timestamp": asset.get("timestamp"),
                "poll_status": asset.get("poll_status", {}),
            }
            for asset in self._all_assets(snapshot)
        ]

    def _fieldbus_rate_analysis(self) -> dict[str, Any]:
        intervals = {
            "fast": self.config.bms.poll_fast_seconds,
            "normal": self.config.bms.poll_normal_seconds,
            "slow": self.config.bms.poll_slow_seconds,
            "bulk": self.config.bms.poll_bulk_seconds,
        }
        groups: dict[str, Any] = {}
        total_requests_per_minute = 0.0
        total_registers_per_minute = 0.0
        total_modbus_bytes_per_minute = 0.0
        total_wire_bytes_per_minute = 0.0
        for poll_class, interval in intervals.items():
            requests = registers = modbus_bytes = 0
            for scope, multiplier in (("bank", len(self.config.bms.racks)), ("rack", len(self.config.bms.racks)), ("environment", 1)):
                points = self.bms_catalog.select(
                    scope=scope, poll_classes={poll_class}, include_reserved=False
                )
                blocks = build_read_blocks(
                    points,
                    max_registers=self.config.bms.max_registers_per_request,
                    max_gap=self.config.bms.max_gap_registers,
                )
                requests += len(blocks) * multiplier
                registers += sum(block.count for block in blocks) * multiplier
                # Modbus TCP ADU: 12-byte request; response is 9 bytes plus 2 bytes/register.
                modbus_bytes += sum(21 + 2 * block.count for block in blocks) * multiplier
            cycles_per_minute = 60.0 / max(interval, 0.001)
            requests_per_minute = requests * cycles_per_minute
            registers_per_minute = registers * cycles_per_minute
            payload_per_minute = modbus_bytes * cycles_per_minute
            # Approximate Ethernet+IPv4+TCP framing for one request and one response.
            wire_per_minute = payload_per_minute + requests_per_minute * 2 * 54
            groups[poll_class] = {
                "interval_seconds": interval,
                "requests_per_cycle": requests,
                "registers_per_cycle": registers,
                "modbus_bytes_per_cycle": modbus_bytes,
                "requests_per_minute": round(requests_per_minute, 2),
                "registers_per_minute": round(registers_per_minute, 2),
                "estimated_wire_bytes_per_minute": round(wire_per_minute, 2),
            }
            total_requests_per_minute += requests_per_minute
            total_registers_per_minute += registers_per_minute
            total_modbus_bytes_per_minute += payload_per_minute
            total_wire_bytes_per_minute += wire_per_minute

        points = sorted(self.pcs_catalog.points, key=lambda point: int(point["address"]))
        pcs_blocks: list[tuple[int, int]] = []
        index = 0
        while index < len(points):
            first = points[index]
            start = int(first["address"])
            end = start + int(first.get("register_count") or 1)
            index += 1
            while index < len(points):
                point = points[index]
                point_start = int(point["address"])
                point_end = point_start + int(point.get("register_count") or 1)
                if point_start > end + 1 or point_end - start > self.config.pcs.max_registers_per_request:
                    break
                end = max(end, point_end)
                index += 1
            pcs_blocks.append((start, end - start))

        device_count = len(self.config.pcs.enabled_devices) if self.config.pcs.enabled else 0
        pcs_requests = len(pcs_blocks) * device_count
        pcs_registers = sum(count for _, count in pcs_blocks) * device_count
        if self.config.pcs.transport == "rtu":
            # FC03 RTU request is 8 bytes. Response is slave+FC+byte-count,
            # register payload and CRC: 5 + 2*count bytes.
            per_device_bytes = sum(13 + 2 * count for _, count in pcs_blocks)
            pcs_modbus_bytes = per_device_bytes * device_count
            pcs_wire_overhead = 0.0
            pcs_transport_note = "Shared RS485 Modbus RTU; slaves are polled sequentially"
        else:
            per_device_bytes = sum(21 + 2 * count for _, count in pcs_blocks)
            pcs_modbus_bytes = per_device_bytes * device_count
            pcs_transport_note = "Persistent Modbus TCP connection(s)"
            pcs_wire_overhead = None

        pcs_cycles = 60.0 / max(self.config.pcs.poll_seconds, 0.001)
        pcs_requests_min = pcs_requests * pcs_cycles
        pcs_registers_min = pcs_registers * pcs_cycles
        pcs_payload_min = pcs_modbus_bytes * pcs_cycles
        if pcs_wire_overhead is None:
            pcs_wire_min = pcs_payload_min + pcs_requests_min * 2 * 54
        else:
            pcs_wire_min = pcs_payload_min
        groups["pcs"] = {
            "enabled": self.config.pcs.enabled,
            "transport": self.config.pcs.transport,
            "configured_devices": len(self.config.pcs.devices),
            "enabled_devices": device_count,
            "interval_seconds": self.config.pcs.poll_seconds,
            "requests_per_cycle": pcs_requests,
            "registers_per_cycle": pcs_registers,
            "modbus_bytes_per_cycle": pcs_modbus_bytes,
            "requests_per_minute": round(pcs_requests_min, 2),
            "registers_per_minute": round(pcs_registers_min, 2),
            "estimated_wire_bytes_per_minute": round(pcs_wire_min, 2),
            "note": pcs_transport_note,
        }
        total_requests_per_minute += pcs_requests_min
        total_registers_per_minute += pcs_registers_min
        total_modbus_bytes_per_minute += pcs_payload_min
        total_wire_bytes_per_minute += pcs_wire_min
        return {
            "transport": f"BMS Modbus TCP + PCS Modbus {self.config.pcs.transport.upper()}",
            "groups": groups,
            "total_requests_per_minute": round(total_requests_per_minute, 2),
            "total_registers_per_minute": round(total_registers_per_minute, 2),
            "modbus_adu_bytes_per_minute": round(total_modbus_bytes_per_minute, 2),
            "estimated_wire_bytes_per_minute": round(total_wire_bytes_per_minute, 2),
            "estimated_average_bits_per_second": round(total_wire_bytes_per_minute * 8 / 60, 2),
            "note": (
                "BMS estimate includes Ethernet/IPv4/TCP framing. PCS RTU estimate is serial frame bytes only. "
                "Retransmissions, switch overhead and RS485 silent intervals are excluded."
            ),
        }

    def data_rate_analysis(self) -> dict[str, Any]:
        intervals = {
            "fast": self.config.bms.poll_fast_seconds,
            "normal": self.config.bms.poll_normal_seconds,
            "slow": self.config.bms.poll_slow_seconds,
            "bulk": self.config.bms.poll_bulk_seconds,
            "pcs": self.config.pcs.poll_seconds,
        }
        stream_bytes_per_minute = 0.0
        groups: dict[str, Any] = {}
        for name, interval in intervals.items():
            stats = self._poll_stats[name]
            average = float(stats.get("average_event_bytes") or stats.get("last_event_bytes") or 0)
            per_minute = average * (60.0 / max(interval, 0.001))
            stream_bytes_per_minute += per_minute
            groups[name] = {
                "interval_seconds": interval,
                "average_event_bytes": round(average, 2),
                "estimated_events_per_minute": round(60.0 / max(interval, 0.001), 2),
                "estimated_bytes_per_minute": round(per_minute, 2),
            }
        compact = self.compact_snapshot()
        full = self.snapshot()
        compact_bytes = len(json.dumps(compact, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        full_bytes = len(json.dumps(full, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        history_assets = [self._history_asset(asset) for asset in self._all_assets(full)]
        history_raw = sum(
            len(json.dumps(asset, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            for asset in history_assets
        )
        history_compressed = sum(
            len(zlib.compress(json.dumps(asset, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6))
            for asset in history_assets
        )
        stored_per_sample = history_compressed if self.config.storage.compress_history else history_raw
        samples_per_day = 86400.0 / max(self.config.storage.sample_interval_seconds, 0.001)
        storage_per_day = stored_per_sample * samples_per_day
        quota = self.store.quota_bytes
        effective_quota = quota * (self.config.storage.quota_high_watermark_percent / 100.0)
        return {
            "field_modbus": self._fieldbus_rate_analysis(),
            "streaming": {
                "transport": "WebSocket initial compact snapshot plus multi-rate delta events",
                "initial_compact_snapshot_bytes": compact_bytes,
                "full_debug_snapshot_bytes": full_bytes,
                "groups": groups,
                "estimated_bytes_per_minute": round(stream_bytes_per_minute, 2),
                "estimated_megabytes_per_minute": round(stream_bytes_per_minute / 1_000_000, 4),
                "estimated_average_bits_per_second": round(stream_bytes_per_minute * 8 / 60, 2),
                "estimated_megabytes_per_day": round(stream_bytes_per_minute * 1440 / 1_000_000, 2),
            },
            "storage": {
                "sample_interval_seconds": self.config.storage.sample_interval_seconds,
                "assets_per_sample": len(history_assets),
                "uncompressed_bytes_per_complete_sample": history_raw,
                "estimated_stored_bytes_per_complete_sample": stored_per_sample,
                "compression_ratio": round(stored_per_sample / history_raw, 4) if history_raw else None,
                "estimated_megabytes_per_day": round(storage_per_day / 1_000_000, 2),
                "estimated_gibibytes_per_day": round(storage_per_day / 1024**3, 4),
                "configured_quota_gb": self.config.storage.quota_gb,
                "quota_high_watermark_percent": self.config.storage.quota_high_watermark_percent,
                "effective_quota_bytes": int(effective_quota),
                "estimated_days_to_high_watermark": round(effective_quota / storage_per_day, 2) if storage_per_day else None,
                "estimated_days_within_full_quota": round(quota / storage_per_day, 2) if storage_per_day else None,
                "runtime_samples": deepcopy(self._storage_sample_stats),
            },
        }

    def health(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        assets = self.assets()
        enabled_assets = [asset for asset in assets if asset.get("enabled", True)]
        online_count = sum(1 for asset in enabled_assets if asset.get("online"))
        return {
            "status": "ok" if online_count == len(enabled_assets) else "degraded",
            "gateway_id": self.config.gateway_id,
            "mode": self.config.mode,
            "sequence": snapshot.get("sequence"),
            "timestamp": snapshot.get("timestamp"),
            "assets_online": online_count,
            "assets_total": len(enabled_assets),
            "assets_configured": len(assets),
            "last_poll_error": self._last_poll_error,
            "polling": deepcopy(self._poll_stats),
            "network": self.config.network.model_dump(),
            "storage": self.store.status(),
            "control_sequence": {
                "enabled": self.config.control_sequence.enabled,
                "full_automatic_sequence_allowed": self.config.control_sequence.allow_full_automatic_sequence,
                "pairs": [pair.model_dump() for pair in self.config.control_sequence.pairs],
            },
        }
