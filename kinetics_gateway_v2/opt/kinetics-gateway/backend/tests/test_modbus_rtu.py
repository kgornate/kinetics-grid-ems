from __future__ import annotations

import json
from pathlib import Path

from app.core.config import GatewayConfig, project_root
from app.protocols.modbus_rtu import ModbusRtuClient, append_crc, crc16_modbus, validate_crc
from app.services.gateway_service import GatewayService
from app.storage.sqlite_store import SQLiteStore


class FakeSerial:
    def __init__(self, response: bytes) -> None:
        self.response = bytearray(response)
        self.written = bytearray()
        self.is_open = True

    def reset_input_buffer(self) -> None:
        return None

    def write(self, payload: bytes) -> int:
        self.written.extend(payload)
        return len(payload)

    def flush(self) -> None:
        return None

    def read(self, count: int) -> bytes:
        if not self.response:
            return b""
        chunk = bytes(self.response[:count])
        del self.response[:count]
        return chunk

    def close(self) -> None:
        self.is_open = False


def test_crc_known_modbus_request():
    payload = bytes.fromhex("01 03 00 00 00 0A")
    assert crc16_modbus(payload) == 0xCDC5
    frame = append_crc(payload)
    assert frame.hex().upper() == "01030000000AC5CD"
    assert validate_crc(frame)


def test_rtu_fc03_read_with_fake_serial():
    response = append_crc(bytes.fromhex("01 03 04 00 2A 00 2B"))
    fake = FakeSerial(response)
    client = ModbusRtuClient(
        device="/dev/fake",
        baudrate=9600,
        timeout=0.1,
        inter_request_delay_ms=0,
        retries=0,
        serial_factory=lambda: fake,
    )
    assert client.read_registers(1, 0x0001, 2, 3) == [42, 43]
    assert validate_crc(bytes(fake.written))
    assert bytes(fake.written[:6]) == bytes.fromhex("01 03 00 01 00 02")


def test_four_pcs_rtu_mock_snapshot(tmp_path: Path):
    payload = json.loads((project_root() / "configs/kinetics_mock.json").read_text())
    payload["storage"]["preferred_root"] = str(tmp_path / "storage")
    payload["storage"]["fallback_root"] = str(tmp_path / "fallback")
    payload["pcs"].update(
        {
            "transport": "rtu",
            "serial": {
                "device": "/dev/pcs_rs485",
                "baudrate": 9600,
                "bytesize": 8,
                "parity": "N",
                "stopbits": 1,
                "inter_request_delay_ms": 20,
                "retries": 1,
            },
            "devices": [
                {"asset_id": f"pcs_{index}", "unit_id": index, "enabled": True}
                for index in range(1, 5)
            ],
        }
    )
    config = GatewayConfig.model_validate(payload)
    service = GatewayService(config, SQLiteStore(config.storage))
    snapshot = service.snapshot()
    assert snapshot["pcs"]["asset_id"] == "pcs_1"
    assert set(snapshot["pcs_devices"]) == {"pcs_1", "pcs_2", "pcs_3", "pcs_4"}
    assert all(len(asset["telemetry"]) == 230 for asset in snapshot["pcs_devices"].values())
    event = service.poll_pcs()
    assert len(event["assets"]) == 4
    assert service.data_rate_analysis()["field_modbus"]["groups"]["pcs"]["configured_devices"] == 4


def test_legacy_tcp_config_expands_to_one_pcs():
    payload = json.loads((project_root() / "configs/kinetics_mock.json").read_text())
    config = GatewayConfig.model_validate(payload)
    assert config.pcs.transport == "tcp"
    assert [(device.asset_id, device.unit_id) for device in config.pcs.devices] == [("pcs_1", 1)]
