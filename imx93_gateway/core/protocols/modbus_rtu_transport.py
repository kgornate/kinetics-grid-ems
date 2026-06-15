"""Modbus RTU transport descriptor helpers."""

from __future__ import annotations

from typing import Any, Dict

from .base_transport import ProtocolDescriptor


def make_modbus_rtu_descriptor(
    serial_port: str,
    baudrate: int = 9600,
    parity: str = "N",
    stopbits: int = 1,
    bytesize: int = 8,
    slave_id: int = 1,
    **metadata: Any,
) -> ProtocolDescriptor:
    connection: Dict[str, Any] = {
        "serial_port": serial_port,
        "baudrate": int(baudrate),
        "parity": parity,
        "stopbits": int(stopbits),
        "bytesize": int(bytesize),
        "slave_id": int(slave_id),
    }
    connection.update(metadata)
    return ProtocolDescriptor(protocol="modbus_rtu", connection=connection)
