from __future__ import annotations

import math
import struct
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.core.acrel_config import AcrelMeterConfig
from app.protocols.modbus_rtu import ModbusRtuClient


# ACREL APM5 Installation/Operation V1.1, printed pp.48-49, 54-55.
# Addresses are zero-based protocol addresses, NOT 4xxxx display references.
MEASUREMENTS = [
    ("voltage_a_v", "V"), ("voltage_b_v", "V"), ("voltage_c_v", "V"),
    ("voltage_ab_v", "V"), ("voltage_bc_v", "V"), ("voltage_ca_v", "V"),
    ("current_a_a", "A"), ("current_b_a", "A"), ("current_c_a", "A"),
    ("current_neutral_a", "A"),
    ("active_power_a_kw", "kW"), ("active_power_b_kw", "kW"),
    ("active_power_c_kw", "kW"), ("active_power_total_kw", "kW"),
    ("reactive_power_a_kvar", "kvar"), ("reactive_power_b_kvar", "kvar"),
    ("reactive_power_c_kvar", "kvar"), ("reactive_power_total_kvar", "kvar"),
    ("apparent_power_a_kva", "kVA"), ("apparent_power_b_kva", "kVA"),
    ("apparent_power_c_kva", "kVA"), ("apparent_power_total_kva", "kVA"),
    ("power_factor_a", ""), ("power_factor_b", ""),
    ("power_factor_c", ""), ("power_factor_total", ""), ("frequency_hz", "Hz"),
]
ENERGIES = [
    ("active_energy_total_kwh", "kWh"), ("active_energy_forward_kwh", "kWh"),
    ("active_energy_reverse_kwh", "kWh"), ("reactive_energy_total_kvarh", "kvarh"),
    ("reactive_energy_forward_kvarh", "kvarh"), ("reactive_energy_reverse_kvarh", "kvarh"),
    ("apparent_energy_total_kvah", "kVAh"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AcrelMeterDriver:
    """FC03-only reader. Never synthesizes hardware values on failure.

    MAX13487E on DEBIX handles direction with the board's default controls.
    No per-byte GPIO/RTS toggling and no writes to meter registers are used.
    One driver owns the port and serializes complete polling cycles.
    """

    def __init__(self, config: AcrelMeterConfig, client: Any = None):
        self.config = config
        self._lock = threading.Lock()
        self._poll_lock = threading.Lock()
        self._last_good: float | None = None
        self._last_energy_good: float | None = None
        self._last_energy_attempt: float | None = None
        self._asset = self._empty_asset()
        self.client = client or ModbusRtuClient(
            device=config.device, baudrate=config.baudrate, parity=config.parity,
            stopbits=config.stopbits, timeout=config.timeout_seconds, retries=config.retries,
            serial_factory=self._open_exclusive,
        )

    def _open_exclusive(self):
        import serial
        return serial.Serial(
            self.config.device, self.config.baudrate, bytesize=8,
            parity=self.config.parity, stopbits=self.config.stopbits,
            timeout=self.config.timeout_seconds, write_timeout=self.config.timeout_seconds,
            exclusive=True,
        )

    def _empty_asset(self):
        c = self.config
        return dict(
            asset_id=c.asset_id, asset_type="energy_meter", vendor="acrel", model="APM520",
            label=c.label, location=c.location, transport="rtu", device=c.device, unit_id=c.unit_id,
            source=c.mode, disabled=not c.enabled, online=False,
            status="disabled" if not c.enabled else "not_polled", timestamp=None,
            last_attempt_at=None, telemetry={}, read_errors=[],
            scaling_validated=c.scaling_validated, writable=False,
        )

    def _decode(self, registers, fields, start, timestamp):
        if len(registers) != len(fields) * 2:
            raise ValueError("Incomplete ACREL register block")
        points = {}
        for index, (key, unit) in enumerate(fields):
            words = list(registers[index * 2:index * 2 + 2])
            ordered = words if self.config.word_order == "big" else words[::-1]
            value = struct.unpack(">f", struct.pack(">HH", *ordered))[0]
            valid = math.isfinite(value)
            points[key] = dict(
                value=value if valid else None, raw=words, unit=unit,
                quality="good" if valid else "bad", timestamp=timestamp,
                address=start + index * 2, data_type="float32", access="R",
                source=self.config.mode,
            )
        return points

    def _mock_registers(self, fields):
        values = {"frequency_hz": 50.0, "active_power_total_kw": 12.0}
        registers = []
        for key, _ in fields:
            value = values.get(key, 1.0 if key.startswith("power_factor") else 0.0)
            words = list(struct.unpack(">HH", struct.pack(">f", value)))
            registers.extend(words if self.config.word_order == "big" else words[::-1])
        return registers

    def _read(self, start, fields, timestamp):
        if self.config.mode == "mock":
            registers = self._mock_registers(fields)
        else:
            registers = self.client.read_registers(
                self.config.unit_id, start, len(fields) * 2, function_code=3
            )
        return self._decode(registers, fields, start, timestamp)

    def poll(self):
        with self._poll_lock:
            with self._lock:
                if not self.config.enabled:
                    return self._view()
                asset = deepcopy(self._asset)
                energy_attempt = self._last_energy_attempt
                energy_good = self._last_energy_good
            now = time.monotonic()
            timestamp = utc_now()
            asset["last_attempt_at"] = timestamp
            errors = []
            try:
                measurements = self._read(0x2000, MEASUREMENTS, timestamp)
            except Exception as error:
                asset.update(online=False, status="offline", read_errors=[
                    {"block": "measurements", "error": str(error)}
                ])
                for point in asset["telemetry"].values():
                    point["quality"] = "bad"
                with self._lock:
                    self._asset = asset
                    return self._view()
            measurement_good = time.monotonic()
            asset["telemetry"].update(measurements)
            asset.update(online=True, timestamp=timestamp)
            if self.config.energy_enabled and (
                energy_attempt is None
                or now - energy_attempt >= self.config.energy_poll_seconds
            ):
                energy_attempt = now
                try:
                    asset["telemetry"].update(self._read(0x3080, ENERGIES, utc_now()))
                    energy_good = time.monotonic()
                except Exception as error:
                    errors.append({"block": "energy", "error": str(error)})
                    energy_good = None
                    for key, _ in ENERGIES:
                        if key in asset["telemetry"]:
                            asset["telemetry"][key]["quality"] = "bad"
            asset["read_errors"] = errors
            with self._lock:
                self._last_good = measurement_good
                self._last_energy_good = energy_good
                self._last_energy_attempt = energy_attempt
                self._asset = asset
                return self._view()

    def _view(self):
        asset = deepcopy(self._asset)
        now = time.monotonic()
        age = None if self._last_good is None else max(0.0, now - self._last_good)
        asset["age_seconds"] = None if age is None else round(age, 3)
        stale = age is not None and age > self.config.stale_after_seconds
        if stale:
            asset.update(online=False, status="stale")
            for point in asset["telemetry"].values():
                point["quality"] = "stale"
        elif asset["online"]:
            bad = any(p["quality"] == "bad" for p in asset["telemetry"].values())
            asset["status"] = "degraded" if bad else "online"
        energy_age = None if self._last_energy_good is None else now - self._last_energy_good
        if self.config.energy_enabled and asset["online"]:
            if energy_age is None:
                asset["status"] = "degraded"
            elif energy_age > self.config.energy_poll_seconds + self.config.stale_after_seconds:
                asset["status"] = "degraded"
                for key, _ in ENERGIES:
                    if key in asset["telemetry"]:
                        asset["telemetry"][key]["quality"] = "stale"
        # Simulation is unambiguous to API and historian consumers.
        if self.config.mode == "mock":
            for point in asset["telemetry"].values():
                if point["quality"] == "good":
                    point["quality"] = "mock"
        return asset

    def snapshot(self):
        with self._lock:
            return self._view()

    def close(self):
        with self._poll_lock:
            self.client.close()
