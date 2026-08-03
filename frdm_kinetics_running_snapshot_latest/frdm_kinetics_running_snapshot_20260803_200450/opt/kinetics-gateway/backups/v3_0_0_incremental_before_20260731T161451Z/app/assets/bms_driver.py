from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.catalog import ProtocolCatalog
from app.core.config import BmsConfig, EndpointConfig, RackEndpointConfig
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


class BmsModbusDriver:
    def __init__(self, config: BmsConfig, catalog: ProtocolCatalog) -> None:
        self.config = config
        self.catalog = catalog
        self.endpoints = self._build_endpoints()
        self.clients: dict[int, ModbusTcpClient] = {}

    def _build_endpoints(self) -> dict[str, Endpoint]:
        endpoints = {
            "bms_bank": Endpoint("bms_bank", "bank", self.config.bau.port, self.config.bau.unit_id),
            "bms_environment": Endpoint(
                "bms_environment", "environment", self.config.power_environment.port,
                self.config.power_environment.unit_id,
            ),
        }
        for rack in self.config.racks:
            endpoints[f"bms_rack_{rack.rack_id}"] = Endpoint(
                f"bms_rack_{rack.rack_id}", "rack", rack.port, rack.unit_id, rack.rack_id
            )
        return endpoints

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
            count = min(remaining, min(125, self.config.max_registers_per_request))
            try:
                words = client.read_registers(endpoint.unit_id, address, count, preferred)
            except ModbusError:
                if not self._fallback_enabled(endpoint):
                    raise
                alternate = 3 if preferred == 4 else 4
                words = client.read_registers(endpoint.unit_id, address, count, alternate)
            values.extend(words)
            address += count
            remaining -= count
        return values

    def _fallback_enabled(self, endpoint: Endpoint) -> bool:
        if endpoint.asset_id == "bms_bank":
            return self.config.bau.read_function_fallback
        if endpoint.asset_id == "bms_environment":
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
                    payload = decode_point(point, words[offset : offset + count], word_order="big")
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
            "asset_type": "bms_bank" if endpoint.scope == "bank" else ("bms_rack" if endpoint.scope == "rack" else "bms_environment"),
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
        try:
            words = client.read_registers(endpoint.unit_id, address, count, preferred)
        except ModbusError:
            if not self._fallback_enabled(endpoint):
                raise
            alternate = 3 if preferred == 4 else 4
            words = client.read_registers(endpoint.unit_id, address, count, alternate)
        payload = decode_point(point, words, word_order="big")
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
            word_order="big",
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
        decoded = decode_point({**point, "element_count": 1, "register_count": 1}, readback, word_order="big")
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
        words = encode_scalar(value, str(point.get("data_type") or "U16"), scale=point.get("scale"), word_order="big")
        client = self._client(endpoint.port)
        address = int(point["address"]) + self.config.address_offset
        if len(words) == 1:
            client.write_single_register(endpoint.unit_id, address, words[0])
        else:
            client.write_multiple_registers(endpoint.unit_id, address, words)
        readback = client.read_registers(endpoint.unit_id, address, len(words), 3)
        decoded = decode_point(point, readback, word_order="big")
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
