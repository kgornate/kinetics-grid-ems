from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from nb_ems_gateway.config.models import ExistingEMSConfig
from .exceptions import ModbusConnectionError, ModbusReadError, ModbusWriteBlockedError

LOGGER = logging.getLogger(__name__)


class RegisterReader(Protocol):
    def read_registers(self, address: int, count: int) -> list[int]: ...
    def close(self) -> None: ...


@dataclass
class ReadOnlyModbusClient:
    config: ExistingEMSConfig

    def __post_init__(self) -> None:
        self._client = None

    def connect(self) -> None:
        try:
            from pymodbus.client import ModbusTcpClient
        except ImportError as exc:
            raise ModbusConnectionError("pymodbus is not installed. Install requirements.txt.") from exc
        self._client = ModbusTcpClient(
            host=self.config.host,
            port=self.config.port,
            timeout=self.config.timeout_sec,
            retries=self.config.retries,
        )
        if not self._client.connect():
            raise ModbusConnectionError(f"Could not connect to EMS at {self.config.host}:{self.config.port}")
        LOGGER.info("Connected to EMS Modbus TCP server %s:%s", self.config.host, self.config.port)

    def read_registers(self, address: int, count: int) -> list[int]:
        if self._client is None:
            self.connect()
        assert self._client is not None
        try:
            if self.config.register_function == "input_registers":
                result = self._client.read_input_registers(address=address, count=count, slave=self.config.unit_id)
            else:
                result = self._client.read_holding_registers(address=address, count=count, slave=self.config.unit_id)
        except TypeError:
            # pymodbus older releases use unit= instead of slave=
            if self.config.register_function == "input_registers":
                result = self._client.read_input_registers(address=address, count=count, unit=self.config.unit_id)
            else:
                result = self._client.read_holding_registers(address=address, count=count, unit=self.config.unit_id)
        except Exception as exc:
            raise ModbusReadError(f"Read failed at address={address}, count={count}: {exc}") from exc
        if result.isError():
            raise ModbusReadError(f"Modbus error at address={address}, count={count}: {result}")
        return list(result.registers)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def write_register(self, *_args, **_kwargs) -> None:
        raise ModbusWriteBlockedError("Writes are blocked in read-only gateway Version 1.")

    def write_registers(self, *_args, **_kwargs) -> None:
        raise ModbusWriteBlockedError("Writes are blocked in read-only gateway Version 1.")


@dataclass
class MockModbusClient:
    values_by_address: dict[int, int]

    def read_registers(self, address: int, count: int) -> list[int]:
        return [int(self.values_by_address.get(addr, 0)) for addr in range(address, address + count)]

    def close(self) -> None:
        pass

    def write_register(self, *_args, **_kwargs) -> None:
        raise ModbusWriteBlockedError("Writes are blocked in mock read-only mode.")
