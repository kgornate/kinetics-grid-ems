from __future__ import annotations

import struct
import threading
import time
from dataclasses import dataclass
from typing import Any


class ModbusRtuError(RuntimeError):
    pass


@dataclass
class ModbusRtuResponse:
    unit_id: int
    function_code: int
    data: bytes


def crc16_modbus(payload: bytes) -> int:
    """Return standard Modbus CRC-16 (polynomial 0xA001)."""
    crc = 0xFFFF
    for byte in payload:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def append_crc(payload: bytes) -> bytes:
    return payload + struct.pack("<H", crc16_modbus(payload))


def validate_crc(frame: bytes) -> bool:
    if len(frame) < 4:
        return False
    expected = struct.unpack("<H", frame[-2:])[0]
    return crc16_modbus(frame[:-2]) == expected


class ModbusRtuClient:
    """Persistent, shared-bus Modbus RTU client for FC03/04/06/16.

    The pyserial dependency is loaded lazily so existing BMS-only/TCP gateway
    deployments continue to start even before PCS RTU commissioning.
    """

    def __init__(
        self,
        device: str,
        baudrate: int,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: int = 1,
        timeout: float = 2.0,
        inter_request_delay_ms: float = 20.0,
        retries: int = 1,
        serial_factory: Any | None = None,
    ) -> None:
        self.device = device
        self.baudrate = int(baudrate)
        self.bytesize = int(bytesize)
        self.parity = str(parity).upper()
        self.stopbits = int(stopbits)
        self.timeout = float(timeout)
        self.inter_request_delay_ms = float(inter_request_delay_ms)
        self.retries = int(retries)
        self._serial_factory = serial_factory
        self._serial: Any | None = None
        self._lock = threading.Lock()
        self._last_request_completed_at = 0.0

    @property
    def effective_inter_request_delay_seconds(self) -> float:
        # Modbus RTU requires at least 3.5 character times of silence. Eleven
        # bits/character safely covers start, 8 data, parity and stop bits.
        protocol_minimum = 3.5 * 11.0 / max(self.baudrate, 1)
        configured = self.inter_request_delay_ms / 1000.0
        return max(protocol_minimum, configured)

    def _open(self) -> Any:
        if self._serial is not None and getattr(self._serial, "is_open", True):
            return self._serial
        if self._serial_factory is not None:
            self._serial = self._serial_factory()
            return self._serial
        try:
            import serial  # type: ignore
        except ImportError as error:
            raise ModbusRtuError(
                "pyserial is required for PCS Modbus RTU; install requirements.txt or run: pip install pyserial"
            ) from error
        try:
            self._serial = serial.Serial(
                port=self.device,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )
        except Exception as error:
            raise ModbusRtuError(f"Cannot open PCS RS485 device {self.device}: {error}") from error
        return self._serial

    def close(self) -> None:
        port, self._serial = self._serial, None
        if port is not None:
            try:
                port.close()
            except Exception:
                pass

    @staticmethod
    def _read_exact(port: Any, count: int) -> bytes:
        chunks: list[bytes] = []
        remaining = count
        while remaining:
            chunk = port.read(remaining)
            if not chunk:
                raise ModbusRtuError(
                    f"Timed out waiting for Modbus RTU response ({remaining} bytes missing)"
                )
            chunks.append(bytes(chunk))
            remaining -= len(chunk)
        return b"".join(chunks)

    def _respect_silent_interval(self) -> None:
        remaining = (
            self.effective_inter_request_delay_seconds
            - (time.monotonic() - self._last_request_completed_at)
        )
        if remaining > 0:
            time.sleep(remaining)

    def _read_response(self, port: Any, unit_id: int, function_code: int) -> ModbusRtuResponse:
        header = self._read_exact(port, 2)
        rx_unit, rx_function = header[0], header[1]

        if rx_function & 0x80:
            tail = self._read_exact(port, 3)  # exception code + CRC
            frame = header + tail
        elif rx_function in {3, 4}:
            byte_count_raw = self._read_exact(port, 1)
            byte_count = byte_count_raw[0]
            tail = self._read_exact(port, byte_count + 2)
            frame = header + byte_count_raw + tail
        elif rx_function in {6, 16}:
            frame = header + self._read_exact(port, 6)
        else:
            # Unknown response length cannot be safely consumed from a shared bus.
            raise ModbusRtuError(f"Unexpected Modbus RTU function code 0x{rx_function:02X}")

        if not validate_crc(frame):
            raise ModbusRtuError("Invalid Modbus RTU CRC")
        if rx_unit != (unit_id & 0xFF):
            raise ModbusRtuError(
                f"Unexpected Modbus RTU slave {rx_unit}; expected {unit_id & 0xFF}"
            )
        if rx_function & 0x80:
            code = frame[2]
            raise ModbusRtuError(f"Modbus exception {code} for FC{function_code:02X}")
        if rx_function != function_code:
            raise ModbusRtuError(
                f"Unexpected function code 0x{rx_function:02X}; expected 0x{function_code:02X}"
            )
        return ModbusRtuResponse(rx_unit, rx_function, frame[2:-2])

    def _request(self, unit_id: int, function_code: int, payload: bytes) -> ModbusRtuResponse:
        if not 1 <= int(unit_id) <= 247:
            raise ValueError("Modbus RTU unit_id must be 1..247")
        request = append_crc(bytes([unit_id & 0xFF, function_code & 0xFF]) + payload)
        with self._lock:
            attempts = self.retries + 1
            last_error: Exception | None = None
            for attempt in range(attempts):
                try:
                    port = self._open()
                    self._respect_silent_interval()
                    if hasattr(port, "reset_input_buffer"):
                        port.reset_input_buffer()
                    written = port.write(request)
                    if written is not None and int(written) != len(request):
                        raise ModbusRtuError(
                            f"Incomplete Modbus RTU write: {written}/{len(request)} bytes"
                        )
                    if hasattr(port, "flush"):
                        port.flush()
                    response = self._read_response(port, unit_id, function_code)
                    self._last_request_completed_at = time.monotonic()
                    return response
                except ModbusRtuError as error:
                    last_error = error
                    self.close()
                    self._last_request_completed_at = time.monotonic()
                    # Device exception responses are deterministic and should not
                    # be retried. CRC/timeouts may be retried according to config.
                    if str(error).startswith("Modbus exception"):
                        raise
                    if attempt + 1 >= attempts:
                        break
                except Exception as error:
                    last_error = error
                    self.close()
                    self._last_request_completed_at = time.monotonic()
                    if attempt + 1 >= attempts:
                        break
            raise ModbusRtuError(
                f"Modbus RTU transport error {self.device}: {last_error}"
            ) from last_error

    def read_registers(
        self,
        unit_id: int,
        address: int,
        count: int,
        function_code: int = 3,
    ) -> list[int]:
        if function_code not in {3, 4}:
            raise ValueError("Read function must be 3 or 4")
        if not 1 <= count <= 125:
            raise ValueError("Modbus read count must be 1..125")
        response = self._request(
            unit_id,
            function_code,
            struct.pack(">HH", address & 0xFFFF, count),
        )
        if not response.data:
            raise ModbusRtuError("Missing RTU byte count")
        byte_count = response.data[0]
        payload = response.data[1:]
        if byte_count != count * 2 or len(payload) != byte_count:
            raise ModbusRtuError("Unexpected Modbus RTU register payload length")
        return list(struct.unpack(">" + "H" * count, payload))

    def write_single_register(self, unit_id: int, address: int, value: int) -> None:
        payload = struct.pack(">HH", address & 0xFFFF, value & 0xFFFF)
        response = self._request(unit_id, 6, payload)
        if response.data != payload:
            raise ModbusRtuError("FC06 RTU write echo mismatch")

    def write_multiple_registers(self, unit_id: int, address: int, values: list[int]) -> None:
        if not values or len(values) > 123:
            raise ValueError("FC16 values must contain 1..123 registers")
        encoded = struct.pack(">" + "H" * len(values), *[value & 0xFFFF for value in values])
        payload = struct.pack(">HHB", address & 0xFFFF, len(values), len(encoded)) + encoded
        response = self._request(unit_id, 16, payload)
        expected = struct.pack(">HH", address & 0xFFFF, len(values))
        if response.data != expected:
            raise ModbusRtuError("FC16 RTU write response mismatch")
