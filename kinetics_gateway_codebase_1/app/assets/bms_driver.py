from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.catalog import ProtocolCatalog
from app.core.config import BmsConfig, BmsAuxEndpointConfig, EndpointConfig, RackEndpointConfig
from app.protocols.codec import decode_point, encode_scalar, validate_value
from app.protocols.modbus_tcp import ModbusError, ModbusTcpClient
from app.protocols.planner import ReadBlock, build_read_blocks

LOGGER = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Endpoint:
    asset_id: str
    scope: str
    port: int
    unit_id: int
    rack_id: int | None = None
    categories: tuple[str, ...] = ()


class BmsModbusDriver:
    def __init__(self, config: BmsConfig, catalog: ProtocolCatalog) -> None:
        self.config = config
        self.catalog = catalog
        self.endpoints = self._build_endpoints()
        self.clients: dict[int, ModbusTcpClient] = {}

    def _build_endpoints(self) -> dict[str, Endpoint]:
        endpoints: dict[str, Endpoint] = {
            # System/BAMS endpoint. For Lineage system_rack this is the single
            # Unit-ID 1 system map. For the legacy Kinetics three-level profile
            # it remains the backward-compatible BAU alias.
            "bms_bank": Endpoint("bms_bank", "bank", self.config.bau.port, self.config.bau.unit_id),
        }

        # Keep the historical per-pair BAU endpoints only for the Kinetics
        # three-level topology. Lineage has one system/BAMS map plus rack Unit
        # IDs; repeating Unit-ID 1 once per rack wastes fieldbus bandwidth and
        # creates duplicate logical bank assets.
        if self.config.architecture == "three_level":
            for rack in self.config.racks:
                endpoints[f"bms_bank_{rack.rack_id}"] = Endpoint(
                    f"bms_bank_{rack.rack_id}",
                    "bank",
                    rack.port,
                    self.config.bau.unit_id,
                    rack.rack_id,
                )

        for rack in self.config.racks:
            endpoints[f"bms_rack_{rack.rack_id}"] = Endpoint(
                f"bms_rack_{rack.rack_id}", "rack", rack.port, rack.unit_id, rack.rack_id
            )

        # Phase 4 supports the exact auxiliary Unit-ID allocation as a config
        # concern. If no explicit devices are supplied, preserve the legacy
        # single environment endpoint that reads every environment category.
        enabled_aux = [device for device in self.config.auxiliary_devices if device.enabled]
        if enabled_aux:
            for device in enabled_aux:
                endpoints[device.asset_id] = Endpoint(
                    device.asset_id,
                    "environment",
                    device.port,
                    device.unit_id,
                    None,
                    (device.category,),
                )
        else:
            endpoints["bms_environment"] = Endpoint(
                "bms_environment",
                "environment",
                self.config.power_environment.port,
                self.config.power_environment.unit_id,
            )
        return endpoints

    @property
    def environment_asset_ids(self) -> list[str]:
        return [asset_id for asset_id, endpoint in self.endpoints.items() if endpoint.scope == "environment"]

    def _client(self, port: int) -> ModbusTcpClient:
        if port not in self.clients:
            self.clients[port] = ModbusTcpClient(
                self.config.host, port, self.config.timeout_seconds, source_ip=self.config.source_ip
            )
        return self.clients[port]

    def _read_chunked(self, client: ModbusTcpClient, endpoint: Endpoint, block: ReadBlock) -> list[int]:
        values: list[int] = []
        remaining = block.count
        address = block.start + self.config.address_offset
        preferred = block.function_code
        while remaining > 0:
            if preferred in {1, 2}:
                count = min(remaining, min(2000, self.config.max_registers_per_request))
                chunk = client.read_bits(endpoint.unit_id, address, count, preferred)
            else:
                count = min(remaining, min(125, self.config.max_registers_per_request))
                try:
                    chunk = client.read_registers(endpoint.unit_id, address, count, preferred)
                except ModbusError:
                    # Kinetics firmware historically allowed an FC03/FC04 fallback.
                    # Discrete-input/coils (FC01/02) are not interchangeable with
                    # register reads, so never apply the fallback to them.
                    if preferred not in {3, 4} or not self._fallback_enabled(endpoint):
                        raise
                    alternate = 3 if preferred == 4 else 4
                    chunk = client.read_registers(endpoint.unit_id, address, count, alternate)
            values.extend(chunk)
            address += count
            remaining -= count
        return values

    def _fallback_enabled(self, endpoint: Endpoint) -> bool:
        if endpoint.asset_id == "bms_bank" or endpoint.asset_id.startswith("bms_bank_"):
            return self.config.bau.read_function_fallback
        if endpoint.scope == "environment":
            aux = next((item for item in self.config.auxiliary_devices if item.asset_id == endpoint.asset_id), None)
            if aux is not None:
                return aux.read_function_fallback
            return self.config.power_environment.read_function_fallback
        rack = next((r for r in self.config.racks if r.rack_id == endpoint.rack_id), None)
        return bool(rack and rack.read_function_fallback)

    def read_asset(
        self,
        asset_id: str,
        *,
        include_slow: bool = False,
        include_bulk: bool = False,
    ) -> dict[str, Any]:
        poll_classes = {"fast", "normal"}
        if include_slow:
            poll_classes.add("slow")
        if include_bulk:
            poll_classes.add("bulk")
        return self.read_asset_classes(asset_id, poll_classes)

    def read_asset_classes(self, asset_id: str, poll_classes: set[str]) -> dict[str, Any]:
        endpoint = self.endpoints[asset_id]
        points = self.catalog.select(scope=endpoint.scope, poll_classes=set(poll_classes))
        if endpoint.categories:
            allowed = set(endpoint.categories)
            points = [point for point in points if str(point.get("category")) in allowed]
        blocks = build_read_blocks(
            points,
            max_registers=self.config.max_registers_per_request,
            max_gap=self.config.max_gap_registers,
        )
        client = self._client(endpoint.port)
        telemetry: dict[str, Any] = {}
        errors: list[dict[str, Any]] = []
        for block in blocks:
            try:
                words = self._read_chunked(client, endpoint, block)
                for point in block.points:
                    offset = int(point["address"]) - block.start
                    count = int(point.get("register_count") or 1)
                    payload = decode_point(
                        point,
                        words[offset : offset + count],
                        word_order=str(point.get("word_order") or self.config.word_order),
                    )
                    telemetry[str(point["key"])] = {
                        **payload,
                        "key": point["key"],
                        "name_en": point.get("name_en"),
                        "name_cn": point.get("name_cn"),
                        "address": point.get("address_hex"),
                        "category": point.get("category"),
                        "access": point.get("access"),
                    }
            except Exception as error:
                LOGGER.warning("BMS read failed asset=%s start=%s count=%s: %s", asset_id, block.start, block.count, error)
                errors.append({"start": block.start, "count": block.count, "error": str(error)})
                for point in block.points:
                    telemetry[str(point["key"])] = {
                        "key": point["key"],
                        "name_en": point.get("name_en"),
                        "name_cn": point.get("name_cn"),
                        "address": point.get("address_hex"),
                        "unit": point.get("unit"),
                        "quality": "bad",
                        "value": None,
                        "raw": None,
                        "bitfields": {},
                    }
        return {
            "asset_id": asset_id,
            "asset_type": (
                "bms_bank"
                if endpoint.scope == "bank"
                else (
                    "bms_rack"
                    if endpoint.scope == "rack"
                    else (endpoint.categories[0] if endpoint.categories else "bms_environment")
                )
            ),
            "rack_id": endpoint.rack_id,
            "online": len(errors) < max(1, len(blocks)),
            "host": self.config.host,
            "port": endpoint.port,
            "unit_id": endpoint.unit_id,
            "timestamp": now_iso(),
            "telemetry": telemetry,
            "read_errors": errors,
            "poll_classes": sorted(poll_classes),
        }


    def read_point(self, asset_id: str, point_key: str) -> dict[str, Any]:
        """Read one catalog point directly for control-stage verification."""
        endpoint = self.endpoints[asset_id]
        point = self.catalog.by_key(point_key, scope=endpoint.scope)
        if not point:
            raise KeyError(f"Unknown BMS point: {point_key}")
        count = int(point.get("register_count") or 1)
        address = int(point["address"]) + self.config.address_offset
        preferred = int(point.get("read_function") or 3)
        client = self._client(endpoint.port)
        if preferred in {1, 2}:
            words = client.read_bits(endpoint.unit_id, address, count, preferred)
        else:
            try:
                words = client.read_registers(endpoint.unit_id, address, count, preferred)
            except ModbusError:
                if preferred not in {3, 4} or not self._fallback_enabled(endpoint):
                    raise
                alternate = 3 if preferred == 4 else 4
                words = client.read_registers(endpoint.unit_id, address, count, alternate)
        payload = decode_point(
            point,
            words,
            word_order=str(point.get("word_order") or self.config.word_order),
        )
        return {
            **payload,
            "asset_id": asset_id,
            "point_key": point["key"],
            "address": point["address_hex"],
            "name_en": point.get("name_en"),
            "name_cn": point.get("name_cn"),
            "timestamp": now_iso(),
        }

    def write_indexed_point(
        self,
        asset_id: str,
        point_key: str,
        index: int,
        value: int | float,
    ) -> dict[str, Any]:
        """Write one element of a contiguous catalog array with readback.

        This is used for BAU Rack1..Rack32 enable controls, whose catalog
        entry is one 32-register array beginning at 0x3005.
        """
        if not self.config.write_enabled:
            raise PermissionError("BMS writes are disabled in configuration")
        endpoint = self.endpoints[asset_id]
        point = self.catalog.by_key(point_key, scope=endpoint.scope)
        if not point:
            raise KeyError(f"Unknown BMS point: {point_key}")
        if "W" not in str(point.get("access", "R")).upper():
            raise PermissionError(f"Point {point_key} is read-only")
        element_count = int(point.get("element_count") or 1)
        register_width = int(point.get("register_width") or 1)
        if not 0 <= int(index) < element_count:
            raise IndexError(f"Index {index} outside 0..{element_count - 1} for {point_key}")
        if register_width != 1:
            raise ValueError("Indexed writes currently support one-register elements only")
        validate_value(point, value)
        words = encode_scalar(
            value,
            str(point.get("data_type") or "U16"),
            scale=point.get("scale"),
            offset=point.get("offset"),
            word_order=str(point.get("word_order") or self.config.word_order),
        )
        address = int(point["address"]) + int(index) + self.config.address_offset
        client = self._client(endpoint.port)
        try:
            client.write_single_register(
                endpoint.unit_id,
                address,
                words[0],
            )
        except ModbusError as error:
            LOGGER.warning(
                "FC06 indexed write failed at 0x%04X; "
                "retrying with FC16: %s",
                address,
                error,
            )
            client.write_multiple_registers(
                endpoint.unit_id,
                address,
                [words[0]],
            )

        readback = client.read_registers(
            endpoint.unit_id,
            address,
            1,
            3,
        )
        decoded = decode_point(
            {**point, "element_count": 1, "register_count": 1},
            readback,
            word_order=str(point.get("word_order") or self.config.word_order),
        )
        return {
            "ok": True,
            "asset_id": asset_id,
            "point_key": point["key"],
            "index": int(index),
            "address": f"0x{address:04X}",
            "written_value": value,
            "encoded_registers": words,
            "readback": decoded,
            "timestamp": now_iso(),
        }

    def write_point(self, asset_id: str, point_key: str, value: int | float) -> dict[str, Any]:
        if not self.config.write_enabled:
            raise PermissionError("BMS writes are disabled in configuration")
        endpoint = self.endpoints[asset_id]
        point = self.catalog.by_key(point_key, scope=endpoint.scope)
        if not point:
            raise KeyError(f"Unknown BMS point: {point_key}")
        if "W" not in str(point.get("access", "R")).upper():
            raise PermissionError(f"Point {point_key} is read-only")
        if int(point.get("element_count") or 1) != 1:
            raise ValueError("Array writes require a dedicated indexed endpoint")
        validate_value(point, value)
        words = encode_scalar(
            value,
            str(point.get("data_type") or "U16"),
            scale=point.get("scale"),
            offset=point.get("offset"),
            word_order=str(point.get("word_order") or self.config.word_order),
        )
        client = self._client(endpoint.port)
        address = int(point["address"]) + self.config.address_offset
        if len(words) == 1:
            client.write_single_register(endpoint.unit_id, address, words[0])
        else:
            client.write_multiple_registers(endpoint.unit_id, address, words)
        readback = client.read_registers(endpoint.unit_id, address, len(words), 3)
        decoded = decode_point(
            point,
            readback,
            word_order=str(point.get("word_order") or self.config.word_order),
        )
        return {
            "ok": True,
            "asset_id": asset_id,
            "point_key": point["key"],
            "address": point["address_hex"],
            "written_value": value,
            "encoded_registers": words,
            "readback": decoded,
            "timestamp": now_iso(),
        }
