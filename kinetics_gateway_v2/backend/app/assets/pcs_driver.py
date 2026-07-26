from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.catalog import ProtocolCatalog
from app.core.config import PcsConfig
from app.protocols.codec import decode_point, encode_scalar, validate_value, width_for_type
from app.protocols.modbus_tcp import ModbusTcpClient

LOGGER = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PcsModbusDriver:
    """PCS driver supports raw FC03 monitoring now and becomes fully decoded through catalog overrides."""

    def __init__(self, config: PcsConfig, catalog: ProtocolCatalog) -> None:
        self.config = config
        self.catalog = catalog
        self.client = ModbusTcpClient(
            config.host, config.port, config.timeout_seconds, source_ip=config.source_ip
        )

    def read_all(self) -> dict[str, Any]:
        points = sorted(self.catalog.points, key=lambda p: int(p["address"]))
        telemetry: dict[str, Any] = {}
        errors: list[dict[str, Any]] = []
        index = 0
        while index < len(points):
            first = points[index]
            start = int(first["address"])
            block_points = [first]
            end = start + int(first.get("register_count") or 1)
            index += 1
            while index < len(points):
                point = points[index]
                point_start = int(point["address"])
                point_end = point_start + int(point.get("register_count") or 1)
                if point_start > end + 1 or point_end - start > self.config.max_registers_per_request:
                    break
                block_points.append(point)
                end = max(end, point_end)
                index += 1
            try:
                words = self.client.read_registers(
                    self.config.unit_id,
                    start + self.config.address_offset,
                    end - start,
                    int(first.get("function_code") or 3),
                )
                for point in block_points:
                    offset = int(point["address"]) - start
                    dtype = str(point.get("data_type") or "UNKNOWN").upper()
                    count = int(point.get("register_count") or 1)
                    if dtype == "UNKNOWN":
                        payload = {
                            "value": words[offset] if count == 1 else words[offset : offset + count],
                            "raw": words[offset] if count == 1 else words[offset : offset + count],
                            "unit": point.get("unit"),
                            "quality": "good",
                            "bitfields": {},
                            "decoding_status": "raw_only",
                        }
                    else:
                        payload = decode_point(point, words[offset : offset + count], word_order=str(point.get("word_order") or "big"))
                        payload["decoding_status"] = "decoded"
                    telemetry[str(point["key"])] = {
                        **payload,
                        "key": point["key"],
                        "name_en": point.get("name_en"),
                        "name_cn": point.get("name_cn"),
                        "address": point.get("address_hex"),
                        "access": point.get("access", "R"),
                    }
            except Exception as error:
                LOGGER.warning("PCS read failed start=%s count=%s: %s", start, end - start, error)
                errors.append({"start": start, "count": end - start, "error": str(error)})
                for point in block_points:
                    telemetry[str(point["key"])] = {
                        "key": point["key"], "name_cn": point.get("name_cn"), "address": point.get("address_hex"),
                        "value": None, "raw": None, "quality": "bad", "decoding_status": "unavailable",
                    }
        return {
            "asset_id": "pcs_1",
            "asset_type": "pcs",
            "online": not errors,
            "host": self.config.host,
            "port": self.config.port,
            "unit_id": self.config.unit_id,
            "timestamp": now_iso(),
            "telemetry": telemetry,
            "read_errors": errors,
            "protocol_status": "fully_decoded" if all(p.get("data_type") != "UNKNOWN" for p in self.catalog.points) else "raw_map_partial_specification",
        }

    def write_point(self, point_key: str, value: int | float) -> dict[str, Any]:
        if not self.config.write_enabled:
            raise PermissionError("PCS writes are disabled until vendor write details are loaded")
        point = self.catalog.by_key(point_key, scope="pcs")
        if not point:
            raise KeyError(f"Unknown PCS point: {point_key}")
        if "W" not in str(point.get("access", "R")).upper():
            raise PermissionError(f"PCS point {point_key} is not marked writable")
        if str(point.get("data_type") or "UNKNOWN").upper() == "UNKNOWN":
            raise ValueError("PCS data type is missing for this point")
        validate_value(point, value)
        words = encode_scalar(
            value,
            str(point["data_type"]),
            scale=point.get("scale"),
            word_order=str(point.get("word_order") or "big"),
        )
        address = int(point["address"]) + self.config.address_offset
        write_function = int(point.get("write_function") or (6 if len(words) == 1 else 16))
        if write_function == 6 and len(words) == 1:
            self.client.write_single_register(self.config.unit_id, address, words[0])
        elif write_function == 16:
            self.client.write_multiple_registers(self.config.unit_id, address, words)
        else:
            raise ValueError(f"Unsupported PCS write function {write_function}")
        return {
            "ok": True,
            "asset_id": "pcs_1",
            "point_key": point["key"],
            "address": point["address_hex"],
            "written_value": value,
            "encoded_registers": words,
            "timestamp": now_iso(),
        }
