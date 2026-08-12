from __future__ import annotations
import math
import random
import time
from typing import Protocol, Any

from nb_ems_gateway.dictionary.register_map import RegisterPoint
from nb_ems_gateway.decoding.float_codec import decode_float32, encode_float32

class RegisterReader(Protocol):
    def read_point(self, point: RegisterPoint) -> list[int]: ...
    def write_point(self, point: RegisterPoint, value: float) -> list[int]: ...
    def read_value(self, point: RegisterPoint, byte_order: str='ABCD') -> float: ...
    def write_value(self, point: RegisterPoint, value: float, byte_order: str='ABCD') -> float: ...
    def close(self) -> None: ...

class MockRegisterReader:
    def __init__(self, byte_order: str='ABCD', source_id: str='mock') -> None:
        self.byte_order = byte_order
        self.source_id = source_id
        self.started = time.time()
        self.values: dict[int, float] = {
            4: 1.0,
            10: 0.0,
            12: 2.0,
            20: 2.0,
            22: 1.0,
            40: 2.0,
            42: 0.0,
            44: 0.0,
            146: 0.0,
            164: 0.0,
            180: 1.0,
            346: 230.0,
            348: 230.0,
            350: 230.0,
        }

    def read_point(self, point: RegisterPoint) -> list[int]:
        if point.address in self.values:
            v = self.values[point.address]
        else:
            t = time.time() - self.started
            name = (point.point_name + ' ' + point.category).lower()
            if 'soc' in name:
                v = 55 + 5 * math.sin(t / 60)
            elif 'soh' in name:
                v = 98
            elif 'phase' in name and 'voltage' in name:
                v = 230 + 0.5 * math.sin(t / 10)
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

    def write_point(self, point: RegisterPoint, value: float) -> list[int]:
        self.values[point.address] = float(value)
        # Simulate vendor control behavior for command-line/mock testing.
        if point.address == 164:
            if int(value) == 1:
                self.values[180] = 1.0
            elif int(value) == 2:
                self.values[180] = 0.0
            self.values[164] = 0.0
        elif point.address == 42:
            self.values[146] = 2.0 if float(value) > 0 else 0.0
            self.values[44] = 0.0 if float(value) > 0 else self.values.get(44, 0.0)
        elif point.address == 44:
            self.values[146] = 1.0 if float(value) > 0 else 0.0
            self.values[42] = 0.0 if float(value) > 0 else self.values.get(42, 0.0)
        elif point.address == 12:
            self.values[146] = {2: 0.0, 3: 2.0, 4: 1.0}.get(int(value), self.values.get(146, 0.0))
        return encode_float32(float(value), self.byte_order)

    def read_value(self, point: RegisterPoint, byte_order: str='ABCD') -> float:
        return decode_float32(self.read_point(point), byte_order or self.byte_order)

    def write_value(self, point: RegisterPoint, value: float, byte_order: str='ABCD') -> float:
        self.write_point(point, value)
        return self.read_value(point, byte_order or self.byte_order)

    def close(self) -> None:
        pass

class ModbusTcpRegisterReader:
    def __init__(self, host: str, port: int, unit_id: int, timeout_sec: float, byte_order: str='ABCD', source_id: str='') -> None:
        from pymodbus.client import ModbusTcpClient
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.byte_order = byte_order
        self.source_id = source_id
        self.client = ModbusTcpClient(host=host, port=port, timeout=timeout_sec)
        self.client.connect()

    def _read_holding_registers_compat(self, address: int, count: int):
        """Call pymodbus read_holding_registers across 2.x/3.x/4.x style APIs.

        Different pymodbus versions use different unit-id names:
        unit, slave, or device_id. Recent versions also make count keyword-only.
        Field rootfs images can have any of these, so we try the known signatures.
        """
        attempts = [
            lambda: self.client.read_holding_registers(address=address, count=count, device_id=self.unit_id),
            lambda: self.client.read_holding_registers(address, count=count, device_id=self.unit_id),
            lambda: self.client.read_holding_registers(address=address, count=count, slave=self.unit_id),
            lambda: self.client.read_holding_registers(address, count=count, slave=self.unit_id),
            lambda: self.client.read_holding_registers(address=address, count=count, unit=self.unit_id),
            lambda: self.client.read_holding_registers(address, count=count, unit=self.unit_id),
            lambda: self.client.read_holding_registers(address, count, slave=self.unit_id),
            lambda: self.client.read_holding_registers(address, count, unit=self.unit_id),
            lambda: self.client.read_holding_registers(address, count),
            lambda: self.client.read_holding_registers(address=address, count=count),
        ]
        last_exc: TypeError | None = None
        for attempt in attempts:
            try:
                return attempt()
            except TypeError as exc:
                last_exc = exc
                continue
        if last_exc is not None:
            raise last_exc
        raise RuntimeError('No pymodbus read_holding_registers signature matched')

    def _write_registers_compat(self, address: int, registers: list[int]):
        """Call pymodbus write_registers across 2.x/3.x/4.x style APIs."""
        attempts = [
            lambda: self.client.write_registers(address=address, values=registers, device_id=self.unit_id),
            lambda: self.client.write_registers(address, registers, device_id=self.unit_id),
            lambda: self.client.write_registers(address=address, values=registers, slave=self.unit_id),
            lambda: self.client.write_registers(address, registers, slave=self.unit_id),
            lambda: self.client.write_registers(address=address, values=registers, unit=self.unit_id),
            lambda: self.client.write_registers(address, registers, unit=self.unit_id),
            lambda: self.client.write_registers(address, registers),
        ]
        last_exc: TypeError | None = None
        for attempt in attempts:
            try:
                return attempt()
            except TypeError as exc:
                last_exc = exc
                continue
        if last_exc is not None:
            raise last_exc
        raise RuntimeError('No pymodbus write_registers signature matched')

    def read_point(self, point: RegisterPoint) -> list[int]:
        rr = self._read_holding_registers_compat(point.address, point.register_qty)
        if rr is None or getattr(rr, 'isError', lambda: False)():
            raise RuntimeError(f'Modbus read failed source={self.source_id} host={self.host}:{self.port} addr={point.address}')
        return list(rr.registers)

    def write_point(self, point: RegisterPoint, value: float) -> list[int]:
        registers = encode_float32(float(value), self.byte_order)
        rr = self._write_registers_compat(point.address, registers)
        if rr is None or getattr(rr, 'isError', lambda: False)():
            raise RuntimeError(f'Modbus write failed source={self.source_id} host={self.host}:{self.port} addr={point.address}')
        return registers

    def read_value(self, point: RegisterPoint, byte_order: str='ABCD') -> float:
        return decode_float32(self.read_point(point), byte_order or self.byte_order)

    def write_value(self, point: RegisterPoint, value: float, byte_order: str='ABCD') -> float:
        self.write_point(point, value)
        return self.read_value(point, byte_order or self.byte_order)

    def close(self) -> None:
        self.client.close()

def build_reader_for_source(config: Any, source: Any, mock: bool) -> RegisterReader:
    if mock:
        return MockRegisterReader(config.decoding.byte_order, getattr(source, 'source_id', 'mock'))
    return ModbusTcpRegisterReader(
        host=source.host,
        port=source.port,
        unit_id=source.unit_id,
        timeout_sec=source.timeout_sec,
        byte_order=config.decoding.byte_order,
        source_id=source.source_id,
    )

def build_readers(config: Any, mock: bool) -> dict[str, RegisterReader]:
    return {s.source_id: build_reader_for_source(config, s, mock) for s in config.active_external_sources()}

# Backward-compatible helper kept for old imports/tests.
def build_reader(config: Any, mock: bool) -> RegisterReader:
    return build_reader_for_source(config, config.active_external_sources()[0], mock)
