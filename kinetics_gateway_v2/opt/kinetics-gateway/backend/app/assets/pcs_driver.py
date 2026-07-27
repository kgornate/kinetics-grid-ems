from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.catalog import ProtocolCatalog
from app.core.config import PcsConfig, PcsDeviceConfig
from app.protocols.codec import decode_point, encode_scalar, validate_value
from app.protocols.modbus_rtu import ModbusRtuClient
from app.protocols.modbus_tcp import ModbusTcpClient

LOGGER = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PcsModbusDriver:
    """Transport-independent PCS driver for one or more PCS assets.

    Modbus RTU uses one shared serial client and polls configured slave IDs
    sequentially. The existing Modbus TCP path remains available for backward
    compatibility with the previously working gateway configuration.
    """

    def __init__(self, config: PcsConfig, catalog: ProtocolCatalog) -> None:
        self.config = config
        self.catalog = catalog
        self._devices = {device.asset_id: device for device in config.devices}
        self._rtu_client: ModbusRtuClient | None = None
        self._tcp_clients: dict[str, ModbusTcpClient] = {}

        if config.transport == "rtu":
            serial = config.serial
            self._rtu_client = ModbusRtuClient(
                device=serial.device,
                baudrate=serial.baudrate,
                bytesize=serial.bytesize,
                parity=serial.parity,
                stopbits=serial.stopbits,
                timeout=config.timeout_seconds,
                inter_request_delay_ms=serial.inter_request_delay_ms,
                retries=serial.retries,
            )

    @property
    def devices(self) -> list[PcsDeviceConfig]:
        return list(self.config.devices)

    @property
    def primary_asset_id(self) -> str:
        return self.config.primary_device.asset_id

    def device(self, asset_id: str | None = None) -> PcsDeviceConfig:
        selected = asset_id or self.primary_asset_id
        try:
            return self._devices[selected]
        except KeyError as error:
            raise KeyError(f"Unknown PCS asset: {selected}") from error

    def _client_for(self, device: PcsDeviceConfig) -> ModbusRtuClient | ModbusTcpClient:
        if self.config.transport == "rtu":
            if self._rtu_client is None:
                raise RuntimeError("PCS Modbus RTU client is not initialized")
            return self._rtu_client
        client = self._tcp_clients.get(device.asset_id)
        if client is None:
            client = ModbusTcpClient(
                self.config.host,
                self.config.port,
                self.config.timeout_seconds,
                source_ip=self.config.source_ip,
            )
            self._tcp_clients[device.asset_id] = client
        return client

    def close(self) -> None:
        if self._rtu_client is not None:
            self._rtu_client.close()
        for client in self._tcp_clients.values():
            client.close()

    def read_all(self, asset_id: str | None = None) -> dict[str, Any]:
        device = self.device(asset_id)
        if not device.enabled:
            return self.disabled_asset(device)

        client = self._client_for(device)
        points = sorted(
            (point for point in self.catalog.points if point.get("poll_enabled", True)),
            key=lambda point: int(point["address"]),
        )
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
                if (
                    point_start > end + 1
                    or point_end - start > self.config.max_registers_per_request
                ):
                    break
                block_points.append(point)
                end = max(end, point_end)
                index += 1
            try:
                words = client.read_registers(
                    device.unit_id,
                    start + self.config.address_offset,
                    end - start,
                    int(first.get("function_code") or 3),
                )
                for point in block_points:
                    offset = int(point["address"]) - start
                    dtype = str(point.get("data_type") or "UNKNOWN").upper()
                    count = int(point.get("register_count") or 1)
                    if dtype == "UNKNOWN":
                        raw = words[offset] if count == 1 else words[offset : offset + count]
                        payload = {
                            "value": raw,
                            "raw": raw,
                            "unit": point.get("unit"),
                            "quality": "good",
                            "bitfields": {},
                            "decoding_status": "raw_only",
                        }
                    else:
                        payload = decode_point(
                            point,
                            words[offset : offset + count],
                            word_order=str(point.get("word_order") or "big"),
                        )
                        payload["decoding_status"] = "decoded"
                    enum_map = point.get("enum") or {}
                    if enum_map and not isinstance(payload.get("value"), list):
                        payload["enum_label"] = enum_map.get(str(payload.get("raw")))
                    if point.get("bitfields"):
                        payload["bitfield_labels"] = {
                            str(bit["key"]): bit.get("name_en") or bit.get("name_cn")
                            for bit in point["bitfields"]
                        }
                    telemetry[str(point["key"])] = {
                        **payload,
                        "key": point["key"],
                        "name_en": point.get("name_en"),
                        "name_cn": point.get("name_cn"),
                        "address": point.get("address_hex"),
                        "category": point.get("category"),
                        "access": point.get("access", "R"),
                        "hardware_validation": point.get("hardware_validation"),
                    }
            except Exception as error:
                LOGGER.warning(
                    "PCS read failed asset=%s transport=%s unit=%s start=%s count=%s: %s",
                    device.asset_id,
                    self.config.transport,
                    device.unit_id,
                    start,
                    end - start,
                    error,
                )
                errors.append({"start": start, "count": end - start, "error": str(error)})
                for point in block_points:
                    telemetry[str(point["key"])] = {
                        "key": point["key"],
                        "name_cn": point.get("name_cn"),
                        "address": point.get("address_hex"),
                        "value": None,
                        "raw": None,
                        "quality": "bad",
                        "decoding_status": "unavailable",
                    }

        result: dict[str, Any] = {
            "asset_id": device.asset_id,
            "asset_type": "pcs",
            "label": device.label,
            "online": not errors,
            "transport": self.config.transport,
            "unit_id": device.unit_id,
            "timestamp": now_iso(),
            "telemetry": telemetry,
            "read_errors": errors,
            "protocol_status": (
                "fully_decoded"
                if all(point.get("data_type") != "UNKNOWN" for point in self.catalog.points)
                else "raw_map_partial_specification"
            ),
            "commissioning_status": self.config.commissioning_status,
        }
        if self.config.transport == "rtu":
            result["serial_device"] = self.config.serial.device
            result["serial_settings"] = {
                "baudrate": self.config.serial.baudrate,
                "bytesize": self.config.serial.bytesize,
                "parity": self.config.serial.parity,
                "stopbits": self.config.serial.stopbits,
            }
        else:
            result["host"] = self.config.host
            result["port"] = self.config.port
        return result

    @staticmethod
    def disabled_asset(device: PcsDeviceConfig) -> dict[str, Any]:
        return {
            "asset_id": device.asset_id,
            "asset_type": "pcs",
            "label": device.label,
            "unit_id": device.unit_id,
            "online": False,
            "disabled": True,
            "timestamp": now_iso(),
            "telemetry": {},
            "read_errors": [],
        }

    def write_point(self, asset_id: str, point_key: str, value: int | float) -> dict[str, Any]:
        device = self.device(asset_id)
        if not device.enabled:
            raise PermissionError(f"PCS asset {asset_id} is disabled")
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
        client = self._client_for(device)
        if write_function == 6 and len(words) == 1:
            client.write_single_register(device.unit_id, address, words[0])
        elif write_function == 16:
            client.write_multiple_registers(device.unit_id, address, words)
        else:
            raise ValueError(f"Unsupported PCS write function {write_function}")
        return {
            "ok": True,
            "asset_id": device.asset_id,
            "transport": self.config.transport,
            "unit_id": device.unit_id,
            "point_key": point["key"],
            "address": point["address_hex"],
            "written_value": value,
            "encoded_registers": words,
            "timestamp": now_iso(),
        }
