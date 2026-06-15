"""
Protocol transport descriptors for EMS assets.

Design goal:
- Describe asset communication protocols in a common way.
- Keep existing working drivers/services unchanged.
- Make future protocol additions, such as Modbus RTU or CAN for BMS/PCS,
  fit behind a small protocol factory instead of spreading conditionals through
  main.py and network layers.

This module intentionally does not open sockets, serial ports, or CAN devices.
The current implementation is a compatibility-safe descriptor layer.
Existing services still own the real Modbus connections. Future extensions can swap
these descriptors for active transport objects without changing config shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional


JsonDict = Dict[str, Any]


@dataclass(frozen=True)
class ProtocolDescriptor:
    """Normalized description of one asset communication protocol."""

    protocol: str
    connection: JsonDict = field(default_factory=dict)
    profile: Optional[str] = None
    vendor: Optional[str] = None

    @staticmethod
    def normalize_protocol(protocol: Optional[str]) -> str:
        text = str(protocol or "").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "tcp": "modbus_tcp",
            "modbus": "modbus_tcp",
            "modbusip": "modbus_tcp",
            "modbus_tcpip": "modbus_tcp",
            "rtu": "modbus_rtu",
            "rs485": "modbus_rtu",
            "serial": "modbus_rtu",
            "socketcan": "can",
            "canbus": "can",
        }
        return aliases.get(text, text or "unknown")

    @classmethod
    def from_mapping(
        cls,
        *,
        protocol: Optional[str],
        connection: Optional[Mapping[str, Any]] = None,
        profile: Optional[str] = None,
        vendor: Optional[str] = None,
    ) -> "ProtocolDescriptor":
        return cls(
            protocol=cls.normalize_protocol(protocol),
            connection=dict(connection or {}),
            profile=profile,
            vendor=vendor,
        )

    @property
    def host(self) -> Optional[str]:
        value = self.connection.get("host") or self.connection.get("ip")
        return str(value) if value is not None else None

    @property
    def port(self) -> Optional[int]:
        value = self.connection.get("port")
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @property
    def unit_id(self) -> Optional[int]:
        value = self.connection.get("unit_id", self.connection.get("slave_id"))
        if value is None:
            return None
        return int(value)

    @property
    def serial_port(self) -> Optional[str]:
        value = self.connection.get("serial_port") or self.connection.get("port")
        return str(value) if value is not None else None

    @property
    def can_interface(self) -> Optional[str]:
        value = self.connection.get("interface") or self.connection.get("channel")
        return str(value) if value is not None else None

    def to_status(self) -> JsonDict:
        return {
            "protocol": self.protocol,
            "vendor": self.vendor,
            "profile": self.profile,
            "connection": dict(self.connection),
            "host": self.host,
            "port": self.port,
            "unit_id": self.unit_id,
            "serial_port": self.serial_port if self.protocol == "modbus_rtu" else None,
            "can_interface": self.can_interface if self.protocol == "can" else None,
        }
