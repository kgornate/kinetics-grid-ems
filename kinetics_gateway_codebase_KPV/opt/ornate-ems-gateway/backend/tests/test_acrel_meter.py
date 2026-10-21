import json
import struct
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.routes import build_router
from app.core.acrel_config import AcrelMeterConfig
from app.assets.acrel_meter import AcrelMeterDriver, MEASUREMENTS, ENERGIES
from app.core.config import GatewayConfig, project_root
from app.protocols.modbus_rtu import ModbusRtuClient, append_crc, validate_crc
from app.security.auth import AuthService
from app.services.gateway_service import GatewayService
from app.storage.sqlite_store import SQLiteStore


class FakeMeter:
    def __init__(self, word_order="big"):
        self.calls = []
        self.fail_measurement = False
        self.fail_energy = False
        self.nan = False
        self.word_order = word_order

    def read_registers(self, unit_id, address, count, function_code):
        self.calls.append((unit_id, address, count, function_code))
        if (address == 0x2000 and self.fail_measurement) or (address == 0x3080 and self.fail_energy):
            raise TimeoutError("Meter disconnected")
        if address == 0x2000:
            values = [231.25, 232.5, 230.75, 400, 401, 399, 12, 13, 14, 0,
                      -1, -2, -3, -6, 1, 2, 3, 6, 2, 3, 4, 9, .9, .91, .92, .93, 50]
            if self.nan:
                values[0] = float("nan")
        else:
            values = [123456.5, 100000, 23456.5, 500, 400, 100, 200000]
        words = []
        for value in values:
            pair = list(struct.unpack(">HH", struct.pack(">f", value)))
            words.extend(pair if self.word_order == "big" else pair[::-1])
        return words

    def close(self):
        pass


@pytest.mark.parametrize("order", ["big", "lsw_first"])
def test_registers_scaling_signed_power_and_primary_energy(order):
    fake = FakeMeter(order)
    meter = AcrelMeterDriver(AcrelMeterConfig(enabled=True, word_order=order), fake)
    asset = meter.poll()
    points = asset["telemetry"]
    assert fake.calls == [(1, 0x2000, 54, 3), (1, 0x3080, 14, 3)]
    assert len(points) == 34
    assert asset["online"] and asset["status"] == "online"
    assert points["voltage_a_v"]["value"] == 231.25
    assert points["active_power_total_kw"]["value"] == -6
    assert points["active_energy_total_kwh"]["value"] == 123456.5
    assert points["active_energy_forward_kwh"]["address"] == 0x3082
    assert asset["location"] == "unassigned" and not asset["scaling_validated"]
    meter.poll()
    assert fake.calls[-1] == (1, 0x2000, 54, 3)
    assert len(fake.calls) == 3  # energy cached for its slower interval


def test_disconnect_never_emits_zero_or_new_good_timestamps_and_recovers():
    fake = FakeMeter()
    meter = AcrelMeterDriver(AcrelMeterConfig(enabled=True), fake)
    before = meter.poll()
    fake.fail_measurement = True
    failed = meter.poll()
    assert not failed["online"]
    assert failed["timestamp"] == before["timestamp"]
    assert failed["last_attempt_at"] != before["last_attempt_at"]
    assert failed["telemetry"]["voltage_a_v"]["value"] == 231.25
    assert all(p["quality"] == "bad" for p in failed["telemetry"].values())
    fake.fail_measurement = False
    assert meter.poll()["online"]


def test_partial_energy_failure_and_nonfinite_values_are_not_good():
    fake = FakeMeter()
    fake.fail_energy = True
    fake.nan = True
    meter = AcrelMeterDriver(AcrelMeterConfig(enabled=True), fake)
    asset = meter.poll()
    assert asset["online"] and asset["status"] == "degraded"
    assert asset["telemetry"]["voltage_a_v"]["value"] is None
    assert asset["telemetry"]["voltage_a_v"]["quality"] == "bad"
    assert asset["read_errors"][0]["block"] == "energy"
    assert "active_energy_total_kwh" not in asset["telemetry"]
    json.dumps(asset, allow_nan=False)


def test_energy_failure_remains_degraded_until_actual_retry_recovers():
    fake = FakeMeter()
    meter = AcrelMeterDriver(AcrelMeterConfig(enabled=True), fake)
    meter.poll()
    meter._last_energy_attempt -= 61
    fake.fail_energy = True
    failed = meter.poll()
    assert failed["telemetry"]["active_energy_total_kwh"]["quality"] == "bad"
    assert meter.poll()["status"] == "degraded"
    fake.fail_energy = False
    meter._last_energy_attempt -= 61
    assert meter.poll()["status"] == "online"


def test_stale_cache_and_expired_energy():
    meter = AcrelMeterDriver(AcrelMeterConfig(enabled=True), FakeMeter())
    meter.poll()
    meter._last_energy_good -= 81
    assert meter.snapshot()["telemetry"]["active_energy_total_kwh"]["quality"] == "stale"
    meter._last_good -= 21
    stale = meter.snapshot()
    assert stale["status"] == "stale" and not stale["online"]
    assert all(p["quality"] == "stale" for p in stale["telemetry"].values())


def test_snapshot_does_not_wait_for_slow_serial_io():
    started, release = threading.Event(), threading.Event()
    class SlowMeter(FakeMeter):
        def read_registers(self, *args, **kwargs):
            started.set()
            assert release.wait(5)
            return super().read_registers(*args, **kwargs)
    meter = AcrelMeterDriver(AcrelMeterConfig(enabled=True), SlowMeter())
    worker = threading.Thread(target=meter.poll)
    worker.start()
    try:
        assert started.wait(2)
        read_done = threading.Event()
        reader = threading.Thread(target=lambda: (meter.snapshot(), read_done.set()))
        reader.start()
        assert read_done.wait(.5), "API cache read blocked behind serial I/O"
    finally:
        release.set()
        worker.join(5)
    reader.join(1)


def test_disabled_and_mock_never_open_serial():
    fake = FakeMeter()
    disabled = AcrelMeterDriver(AcrelMeterConfig(), fake)
    assert disabled.poll()["disabled"]
    mock = AcrelMeterDriver(AcrelMeterConfig(enabled=True, mode="mock"), fake)
    assert mock.poll()["telemetry"]["frequency_hz"]["quality"] == "mock"
    assert fake.calls == []


@pytest.mark.parametrize("values", [
    {"unit_id": 0}, {"device": "/dev/ttyLP0"}, {"poll_seconds": 0},
    {"poll_seconds": 30}, {"baudrate": 12345}, {"timeout_seconds": float("nan")},
])
def test_invalid_settings_rejected(values):
    with pytest.raises(ValidationError):
        AcrelMeterConfig(**values)


def make_service(tmp_path):
    payload = json.loads((project_root() / "configs/elecod_lineage_4pair_sil.json").read_text())
    payload["mode"] = "mock"
    payload["meter"] = {"enabled": True}
    payload["storage"].update(
        preferred_mount_point=str(tmp_path / "missing"),
        fallback_root=str(tmp_path / "data"), require_preferred_mount=False,
    )
    payload["security"]["allow_dev_default_credentials"] = True
    config = GatewayConfig.model_validate(payload)
    service = GatewayService(config, SQLiteStore(config.storage))
    service.meter_driver.client = FakeMeter()
    return service


def test_integration_cache_delta_history_restart_and_write_boundary(tmp_path):
    service = make_service(tmp_path)
    event = service.poll_meter()
    assert event["poll_class"] == "meter"
    assert event["assets"][0]["telemetry"]["frequency_hz"]["v"] == 50
    assert service.snapshot()["meters"]["acrel_meter_1"]["online"]
    assert service.compact_snapshot()["meters"]["acrel_meter_1"]["online"]
    assert any(a["asset_id"] == "acrel_meter_1" for a in service.assets())
    service._store_snapshot_if_due(service.snapshot(), force=True)
    row = service.store.query_telemetry("acrel_meter_1", limit=1)[0]
    assert row["payload"]["source"] == "hardware"  # global BESS mock does not simulate meter
    assert row["payload"]["telemetry"]["voltage_a_v"]["value"] == 231.25
    reopened = SQLiteStore(service.config.storage)
    assert reopened.query_telemetry("acrel_meter_1", limit=1)
    with pytest.raises(PermissionError, match="read-only"):
        service.execute_control("internal", "acrel_meter_1", "reset", 1)
    assert len(service.snapshot()["racks"]) == 4
    assert len(service.snapshot()["pcs_devices"]) == 4
    rates = service.refresh_data_rate_analysis()
    assert rates["field_modbus"]["groups"]["meter"]["requests_per_minute"] == 13
    assert rates["streaming"]["groups"]["meter"]["interval_seconds"] == 5


def test_authenticated_meter_api_and_existing_historian(tmp_path):
    service = make_service(tmp_path)
    service.poll_meter()
    service._store_snapshot_if_due(service.snapshot(), force=True)
    app = FastAPI()
    app.include_router(build_router(service, AuthService(service.config)))
    with TestClient(app) as http:
        assert http.get("/api/meters").status_code == 401
        token = http.post("/api/auth/login", json={"username": "customer", "password": "Customer@123"}).json()["access_token"]
        headers = {"Authorization": "Bearer " + token}
        for path in ["/api/meters", "/api/meters/acrel_meter_1", "/api/meters/acrel_meter_1/history", "/api/historian/acrel_meter_1"]:
            assert http.get(path, headers=headers).status_code == 200
        assert http.get("/api/meters/config", headers=headers).status_code == 403
        assert http.get("/api/meters/missing", headers=headers).status_code == 404
        assert http.get("/api/meters/acrel_meter_1/history?limit=5001", headers=headers).status_code == 422
        assert http.post("/api/control/acrel_meter_1/reset", json={"value": 1}, headers=headers).status_code == 403
        token = http.post("/api/auth/login", json={"username": "internal", "password": "Internal@123"}).json()["access_token"]
        headers = {"Authorization": "Bearer " + token}
        assert http.get("/api/meters/config", headers=headers).json()["poll_seconds"] == 5
        assert http.post("/api/control/acrel_meter_1/reset", json={"value": 1}, headers=headers).status_code == 403


def test_real_rtu_framing_and_corrupt_crc():
    class Wire:
        is_open = True
        corrupt = False
        data = b""
        def reset_input_buffer(self): self.data = b""
        def write(self, request):
            assert validate_crc(request)
            assert request[:6] == bytes.fromhex("010320000036")
            self.data = append_crc(b"\x01\x03\x6c" + b"\x00" * 108)
            if self.corrupt:
                self.data = self.data[:-1] + bytes([self.data[-1] ^ 1])
            return len(request)
        def flush(self): pass
        def read(self, count):
            result, self.data = self.data[:count], self.data[count:]
            return result
        def close(self): pass
    wire = Wire()
    client = ModbusRtuClient("/dev/test", 9600, retries=0, serial_factory=lambda: wire)
    meter = AcrelMeterDriver(AcrelMeterConfig(enabled=True, energy_enabled=False), client)
    assert meter.poll()["online"]
    wire.corrupt = True
    failed = meter.poll()
    assert not failed["online"] and "CRC" in failed["read_errors"][0]["error"]


def test_shared_pcs_serial_bus_rejected():
    with pytest.raises(ValidationError, match="same serial bus"):
        GatewayConfig.model_validate({
            "meter": {"enabled": True},
            "pcs": {"enabled": True, "transport": "rtu", "serial": {"device": "/dev/ttyLP6"}},
        })


def test_lifespan_starts_meter_independently_and_closes_port(tmp_path, monkeypatch):
    import asyncio
    import app.main as main
    service = make_service(tmp_path)
    calls = []
    original = service.meter_driver.close
    def close():
        calls.append("closed")
        original()
    service.meter_driver.close = close
    monkeypatch.setattr(main, "service", service)
    monkeypatch.setattr(main, "store", service.store)
    monkeypatch.setattr(main, "config", service.config)
    async def exercise():
        async with main.lifespan(main.app):
            for _ in range(100):
                if service.meters()["acrel_meter_1"]["online"]:
                    break
                await asyncio.sleep(.02)
            assert service.meters()["acrel_meter_1"]["online"]
    asyncio.run(exercise())
    assert calls == ["closed"]
