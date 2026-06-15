"""CAN transport descriptor helpers."""

from __future__ import annotations

from typing import Any, Dict

from .base_transport import ProtocolDescriptor


def make_can_descriptor(interface: str = "can0", bitrate: int = 500000, **metadata: Any) -> ProtocolDescriptor:
    connection: Dict[str, Any] = {"interface": interface, "bitrate": int(bitrate)}
    connection.update(metadata)
    return ProtocolDescriptor(protocol="can", connection=connection)
