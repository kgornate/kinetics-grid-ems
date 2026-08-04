from __future__ import annotations

import socket
import struct
import threading
from dataclasses import dataclass


class ModbusError(RuntimeError):
    pass


@dataclass
class ModbusResponse:
    unit_id: int
    function_code: int
    data: bytes


class ModbusTcpClient:
    """Dependency-free persistent Modbus TCP client for FC03/04/06/16."""

    def __init__(
        self,
        host: str,
        port: int = 502,
        timeout: float = 2.0,
        source_ip: str | None = None,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self.source_ip = source_ip
        self._transaction = 0
        self._lock = threading.Lock()
        self._sock: socket.socket | None = None

    def _next_transaction(self) -> int:
        self._transaction = (self._transaction + 1) & 0xFFFF
        return self._transaction

    def _connect(self) -> socket.socket:
        if self._sock is not None:
            return self._sock
        source_address = (self.source_ip, 0) if self.source_ip else None
        sock = socket.create_connection(
            (self.host, self.port), timeout=self.timeout, source_address=source_address
        )
        sock.settimeout(self.timeout)
        self._sock = sock
        return sock

    def close(self) -> None:
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def _request(self, unit_id: int, function_code: int, payload: bytes) -> ModbusResponse:
        with self._lock:
            transaction = self._next_transaction()
            pdu = bytes([function_code]) + payload
            mbap = struct.pack(">HHHB", transaction, 0, len(pdu) + 1, unit_id & 0xFF)
            for attempt in range(2):
                try:
                    sock = self._connect()
                    sock.sendall(mbap + pdu)
                    header = self._recv_exact(sock, 7)
                    rx_transaction, protocol_id, length, rx_unit = struct.unpack(">HHHB", header)
                    if protocol_id != 0 or rx_transaction != transaction:
                        raise ModbusError("Invalid Modbus TCP response header")
                    body = self._recv_exact(sock, length - 1)
                    if not body:
                        raise ModbusError("Empty Modbus response")
                    rx_function = body[0]
                    if rx_function & 0x80:
                        code = body[1] if len(body) > 1 else -1
                        raise ModbusError(f"Modbus exception {code} for FC{function_code:02X}")
                    if rx_function != function_code:
                        raise ModbusError(f"Unexpected function code {rx_function:02X}")
                    return ModbusResponse(rx_unit, rx_function, body[1:])
                except (OSError, socket.timeout) as error:
                    self.close()
                    if attempt == 0:
                        continue
                    raise ModbusError(
                        f"Modbus TCP transport error {self.host}:{self.port}: {error}"
                    ) from error
                except ModbusError:
                    self.close()
                    raise
            raise ModbusError("Modbus request failed")

    @staticmethod
    def _recv_exact(sock: socket.socket, count: int) -> bytes:
        chunks: list[bytes] = []
        remaining = count
        while remaining:
            chunk = sock.recv(remaining)
            if not chunk:
                raise OSError("Connection closed before full response")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def read_registers(self, unit_id: int, address: int, count: int, function_code: int = 3) -> list[int]:
        if function_code not in {3, 4}:
            raise ValueError("Read function must be 3 or 4")
        if not 1 <= count <= 125:
            raise ValueError("Modbus read count must be 1..125")
        response = self._request(unit_id, function_code, struct.pack(">HH", address & 0xFFFF, count))
        if not response.data:
            raise ModbusError("Missing byte count")
        byte_count = response.data[0]
        payload = response.data[1:]
        if byte_count != count * 2 or len(payload) != byte_count:
            raise ModbusError("Unexpected Modbus register payload length")
        return list(struct.unpack(">" + "H" * count, payload))

    def write_single_register(self, unit_id: int, address: int, value: int) -> None:
        payload = struct.pack(">HH", address & 0xFFFF, value & 0xFFFF)
        response = self._request(unit_id, 6, payload)
        if response.data != payload:
            raise ModbusError("FC06 write echo mismatch")

    def write_multiple_registers(self, unit_id: int, address: int, values: list[int]) -> None:
        if not values or len(values) > 123:
            raise ValueError("FC16 values must contain 1..123 registers")
        encoded = struct.pack(">" + "H" * len(values), *[v & 0xFFFF for v in values])
        payload = struct.pack(">HHB", address & 0xFFFF, len(values), len(encoded)) + encoded
        response = self._request(unit_id, 16, payload)
        expected = struct.pack(">HH", address & 0xFFFF, len(values))
        if response.data != expected:
            raise ModbusError("FC16 write response mismatch")
