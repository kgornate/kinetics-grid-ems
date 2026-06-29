from __future__ import annotations

from nb_ems_gateway.config.models import AppConfig
from nb_ems_gateway.decoding.float32_decoder import Float32Decoder
from nb_ems_gateway.dictionary.register_map import RegisterMap
from nb_ems_gateway.protocol.modbus_client import MockModbusClient, ReadOnlyModbusClient, RegisterReader


def build_reader(config: AppConfig, register_map: RegisterMap, mock: bool = False) -> RegisterReader:
    if mock:
        return MockModbusClient(values_by_address=_build_mock_registers(config, register_map))
    return ReadOnlyModbusClient(config.existing_ems)


def _build_mock_registers(config: AppConfig, register_map: RegisterMap) -> dict[int, int]:
    decoder_order = config.decoding.byte_order
    values: dict[int, int] = {}
    for point in register_map.points:
        simulated_value = _mock_value_for_point(point.point_name, point.address)
        hi, lo = Float32Decoder.encode(simulated_value, byte_order=decoder_order)
        values[point.address] = hi
        values[point.address + 1] = lo
    return values


def _mock_value_for_point(point_name: str, address: int) -> float:
    lower = point_name.lower()
    if "soc" in lower:
        return 62.5
    if "frequency" in lower:
        return 50.0
    if "voltage" in lower:
        return 400.0
    if "current" in lower:
        return 12.0
    if "power" in lower:
        return 25.0
    if "temperature" in lower or "temp" in lower:
        return 28.0
    if "insulation" in lower:
        return 5.0
    if "status" in lower or "alarm" in lower or "fault" in lower:
        return 0.0
    return float(address % 100)
