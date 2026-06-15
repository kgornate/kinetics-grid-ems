"""Modbus TCP transport descriptor helpers."""

from __future__ import annotations

from typing import Any, Dict

from .base_transport import ProtocolDescriptor


def make_modbus_tcp_descriptor(host: str, port: int = 502, unit_id: int = 1, **metadata: Any) -> ProtocolDescriptor:
    connection: Dict[str, Any] = {"host": host, "port": int(port), "unit_id": int(unit_id)}
    connection.update(metadata)
    return ProtocolDescriptor(protocol="modbus_tcp", connection=connection)
