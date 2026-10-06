from __future__ import annotations

from typing import Any

from app.assets.normalized import AssetCapabilities, PcsState
from app.assets.pcs_driver import PcsModbusDriver


class ElecodPcsAdapter:
    """Normalized Elecod PCS adapter for the frozen pair-control architecture."""

    capabilities = AssetCapabilities(
        telemetry=True,
        alarms=True,
        writable=True,
        active_power_control=True,
        reactive_power_control=True,
        power_factor_control=True,
        on_grid_control=True,
        off_grid_control=True,
        grid_forming_vf=True,
        grid_forming_vsg=True,
        notes=(
            "Elecod active-power command is percentage of rated power at register 3050.",
            "Positive=discharge / negative=charge is strongly indicated by V2.7.0 but remains commissioning-gated.",
            "FC06 is the default for 5050/5051 because V2.7.0 revision history conflicts with the section 4.7 FC05 example.",
        ),
    )

    def __init__(
        self,
        driver: PcsModbusDriver,
        *,
        rated_power_kw: float,
        power_sign_validated: bool = False,
        positive_power_is_discharge: bool = True,
    ) -> None:
        if rated_power_kw <= 0:
            raise ValueError("rated_power_kw must be positive")
        self.driver = driver
        self.rated_power_kw = float(rated_power_kw)
        self.power_sign_validated = bool(power_sign_validated)
        self.positive_power_is_discharge = bool(positive_power_is_discharge)

    @staticmethod
    def _numeric(point: dict[str, Any]) -> float | None:
        value = point.get("value")
        return float(value) if value is not None else None

    @staticmethod
    def _bit(raw: int | None, bit: int) -> bool | None:
        if raw is None:
            return None
        return bool((int(raw) >> bit) & 1)

    def _vendor_power_to_gateway_kw(self, value: float | None) -> float | None:
        if value is None:
            return None
        return float(value) if self.positive_power_is_discharge else -float(value)

    def _gateway_power_to_vendor_kw(self, value: float) -> float:
        return float(value) if self.positive_power_is_discharge else -float(value)

    def state(self, asset_id: str) -> PcsState:
        read_keys = ["status_word", "total_active_power", "total_reactive_power", "dc_voltage", "dc_current", "dc_bus_voltage"]
        points: dict[str, dict[str, Any]] = {}
        errors: list[str] = []
        for key in read_keys:
            try:
                points[key] = self.driver.read_point(asset_id, key)
            except Exception as error:
                errors.append(f"{key}: {error}")
        status_raw = None
        if "status_word" in points and points["status_word"].get("raw") is not None:
            status_raw = int(points["status_word"]["raw"])

        def num(key: str) -> float | None:
            return self._numeric(points[key]) if key in points else None

        return PcsState(
            asset_id=asset_id,
            online=not errors,
            running=self._bit(status_raw, 6),
            charging=self._bit(status_raw, 5),
            faulted=self._bit(status_raw, 7),
            standby=self._bit(status_raw, 10),
            shutdown=self._bit(status_raw, 11),
            off_grid=self._bit(status_raw, 4),
            dc_relay_connected=self._bit(status_raw, 2),
            ac_relay_connected=self._bit(status_raw, 3),
            dc_precharge_connected=self._bit(status_raw, 0),
            actual_active_power_kw=self._vendor_power_to_gateway_kw(num("total_active_power")),
            actual_reactive_power_kvar=num("total_reactive_power"),
            dc_voltage_v=num("dc_voltage"),
            dc_current_a=num("dc_current"),
            dc_bus_voltage_v=num("dc_bus_voltage"),
            raw_status=status_raw,
            raw={"points": points, "errors": errors},
        )

    def configure_on_grid_pq(self, asset_id: str) -> list[dict[str, Any]]:
        # Elecod V2.7.0: 3157=0 selects on-grid, 3159=0 selects PQ,
        # and 3152=2 selects reactive-power control for Q setpoint operation.
        return [
            self.driver.write_point(asset_id, "grid_mode_command", 0),
            self.driver.write_point(asset_id, "on_grid_control_mode", 0),
            self.driver.write_point(asset_id, "reactive_mode", 2),
            self.driver.write_point(asset_id, "reactive_power_setpoint_percent", 0.0),
        ]

    def configure_off_grid_vf(self, asset_id: str) -> list[dict[str, Any]]:
        return [
            self.driver.write_point(asset_id, "grid_mode_command", 1),
            self.driver.write_point(asset_id, "off_grid_control_mode", 1),
        ]

    def configure_off_grid_vsg(self, asset_id: str) -> list[dict[str, Any]]:
        return [
            self.driver.write_point(asset_id, "grid_mode_command", 1),
            self.driver.write_point(asset_id, "off_grid_control_mode", 0),
        ]

    def start(self, asset_id: str) -> dict[str, Any]:
        return self.driver.write_point(asset_id, "power_on_off_command", 0xFF00)

    def stop(self, asset_id: str) -> dict[str, Any]:
        return self.driver.write_point(asset_id, "power_on_off_command", 0x0000)

    def standby(self, asset_id: str) -> dict[str, Any]:
        return self.driver.write_point(asset_id, "standby_shutdown_command", 0xFF00)

    def shutdown(self, asset_id: str) -> dict[str, Any]:
        return self.driver.write_point(asset_id, "standby_shutdown_command", 0x0000)

    def kw_to_vendor_percent(self, power_kw: float) -> float:
        """Convert the gateway's vendor-neutral kW setpoint to Elecod percent.

        The returned value is engineering percent; PcsModbusDriver applies the
        catalog scale 0.1 to encode register 3050.
        """
        percent = float(power_kw) / self.rated_power_kw * 100.0
        if abs(percent) > 120.0 + 1e-9:
            raise ValueError(f"Requested {power_kw} kW exceeds Elecod +/-120% command range")
        return percent

    def set_active_power_kw(self, asset_id: str, power_kw: float) -> dict[str, Any]:
        if not self.power_sign_validated:
            raise PermissionError(
                "Elecod active-power sign has not been hardware-validated; enable only after low-power charge/discharge commissioning"
            )
        vendor_kw = self._gateway_power_to_vendor_kw(float(power_kw))
        percent = self.kw_to_vendor_percent(vendor_kw)
        result = self.driver.write_point(asset_id, "active_power_setpoint_percent", percent)
        return {**result, "requested_power_kw": power_kw, "vendor_percent": percent, "rated_power_kw": self.rated_power_kw}

    def set_zero_power(self, asset_id: str) -> dict[str, Any]:
        # Zero is direction-independent and can be written before sign validation.
        result = self.driver.write_point(asset_id, "active_power_setpoint_percent", 0.0)
        return {**result, "requested_power_kw": 0.0, "vendor_percent": 0.0, "rated_power_kw": self.rated_power_kw}

    def read_power_setpoint_kw(self, asset_id: str) -> dict[str, Any]:
        point = self.driver.read_point(asset_id, "active_power_setpoint_percent")
        percent = point.get("value")
        vendor_kw = None if percent is None else float(percent) * self.rated_power_kw / 100.0
        gateway_kw = self._vendor_power_to_gateway_kw(vendor_kw)
        return {**point, "value_kw": gateway_kw, "vendor_percent": percent, "rated_power_kw": self.rated_power_kw}

    def set_reactive_power_kvar(self, asset_id: str, reactive_kvar: float) -> dict[str, Any]:
        percent = float(reactive_kvar) / self.rated_power_kw * 100.0
        if abs(percent) > 120.0 + 1e-9:
            raise ValueError(f"Requested {reactive_kvar} kvar exceeds Elecod +/-120% reactive command range")
        result = self.driver.write_point(asset_id, "reactive_power_setpoint_percent", percent)
        return {**result, "requested_reactive_kvar": reactive_kvar, "vendor_percent": percent, "rated_power_kw": self.rated_power_kw}

    def set_power_factor(self, asset_id: str, power_factor: float) -> list[dict[str, Any]]:
        pf = float(power_factor)
        if pf < -1.0 or pf > 1.0:
            raise ValueError("power_factor must be between -1.0 and 1.0")
        return [
            self.driver.write_point(asset_id, "reactive_mode", 1),
            self.driver.write_point(asset_id, "power_factor_setpoint", pf),
        ]
