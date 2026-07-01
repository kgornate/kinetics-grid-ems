from __future__ import annotations

import math
import random
import time
from typing import Protocol

from nb_ems_gateway.decoding.float_codec import encode_float32
from nb_ems_gateway.dictionary.register_map import RegisterPoint


class RegisterReader(Protocol):
    def read_point(self, point: RegisterPoint) -> list[int]: ...
    def write_point(self, point: RegisterPoint, registers: list[int]) -> None: ...
    def close(self) -> None: ...


class MockRegisterReader:
    def __init__(self, byte_order: str = 'ABCD') -> None:
        self.byte_order = byte_order
        self.started = time.time()
        self._written_registers: dict[int, list[int]] = {}

    def read_point(self, point: RegisterPoint) -> list[int]:
        if point.address in self._written_registers:
            return list(self._written_registers[point.address])

        t = time.time() - self.started
        name = (point.point_name + ' ' + point.category).lower()
        if 'soc' in name:
            v = 55 + 5 * math.sin(t / 60)
        elif 'soh' in name:
            v = 98
        elif 'voltage' in name:
            v = 720 + 3 * math.sin(t / 30)
        elif 'current' in name:
            v = 12 * math.sin(t / 10)
        elif 'power' in name:
            v = 50 * math.sin(t / 20)
        elif 'temp' in name:
            v = 28 + 2 * math.sin(t / 45)
        elif 'fault' in name or 'alarm' in name:
            v = 0
        elif 'status' in name or 'mode' in name or 'enable' in name:
            v = 1
        else:
            v = float((point.address % 100) + random.random() * 0.01)
        return encode_float32(v, self.byte_order)

    def write_point(self, point: RegisterPoint, registers: list[int]) -> None:
        if len(registers) != point.register_qty:
            raise ValueError(f'Expected {point.register_qty} registers for {point.signal_name}, got {len(registers)}')
        self._written_registers[point.address] = list(registers)

    def close(self) -> None:
        pass


class ModbusTcpRegisterReader:
    def __init__(self, host: str, port: int, unit_id: int, timeout_sec: float, byte_order: str = 'ABCD') -> None:
        from pymodbus.client import ModbusTcpClient

        self.unit_id = unit_id
        self.client = ModbusTcpClient(host=host, port=port, timeout=timeout_sec)
        self.client.connect()

    def read_point(self, point: RegisterPoint) -> list[int]:
        try:
            rr = self.client.read_holding_registers(point.address, point.register_qty, slave=self.unit_id)
        except TypeError:
            rr = self.client.read_holding_registers(point.address, point.register_qty, unit=self.unit_id)
        if rr is None or getattr(rr, 'isError', lambda: False)():
            raise RuntimeError(f'Modbus read failed addr={point.address}')
        return list(rr.registers)

    def write_point(self, point: RegisterPoint, registers: list[int]) -> None:
        if len(registers) != point.register_qty:
            raise ValueError(f'Expected {point.register_qty} registers for {point.signal_name}, got {len(registers)}')
        try:
            wr = self.client.write_registers(point.address, list(registers), slave=self.unit_id)
        except TypeError:
            wr = self.client.write_registers(point.address, list(registers), unit=self.unit_id)
        if wr is None or getattr(wr, 'isError', lambda: False)():
            raise RuntimeError(f'Modbus write failed addr={point.address}')

    def close(self) -> None:
        self.client.close()


def build_reader(config, mock: bool) -> RegisterReader:
    if mock:
        return MockRegisterReader(config.decoding.byte_order)
    return ModbusTcpRegisterReader(
        config.existing_ems.host,
        config.existing_ems.port,
        config.existing_ems.unit_id,
        config.existing_ems.timeout_sec,
        config.decoding.byte_order,
    )
