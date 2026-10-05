from __future__ import annotations

from typing import Any

from app.assets.bms_driver import BmsModbusDriver
from app.assets.normalized import AssetCapabilities, BatteryRackState, PreparationResult


LINEAGE_STATE_LABELS = {
    0x1111: "NoChg",
    0x2222: "NoDchg",
    0x5555: "Standby",
    0xAAAA: "Fault",
    0xBBBB: "Normal",
    0xCCCC: "Warn",
}
LINEAGE_OPERATING_LABELS = {1: "Open", 2: "Standby", 3: "Charge", 4: "Discharge"}


class LineageBmsAdapter:
    """Vendor-neutral battery adapter over the Lineage V05 register catalog.

    The V05 workbook exposes rack state, dynamic P/I limits and main-contactor
    feedback, but it does *not* expose a normal EMS precharge command/success
    state equivalent to the Kinetics BAU sequence. Therefore preparation is
    observational until Lineage supplies the approved startup handshake.
    """

    capabilities = AssetCapabilities(
        telemetry=True,
        alarms=True,
        writable=True,
        explicit_precharge_command=False,
        automatic_precharge_observable=True,
        forced_contactor_control=True,
        fault_reset=True,
        cell_level_telemetry=True,
        auxiliary_assets=True,
        notes=(
            "V05 has no normal EMS precharge command or explicit precharge-success state.",
            "Forced main-contactor writes are commissioning/maintenance functions and must not substitute for an approved precharge sequence.",
            "FLOAT32 word order and current sign require commissioning confirmation.",
        ),
    )

    def __init__(
        self,
        driver: BmsModbusDriver,
        *,
        allow_forced_contactor_control: bool = False,
    ) -> None:
        self.driver = driver
        self.allow_forced_contactor_control = bool(allow_forced_contactor_control)

    @staticmethod
    def _value(point: dict[str, Any] | None) -> Any:
        return None if not point else point.get("value")

    def _read(self, rack_id: int, key: str) -> dict[str, Any]:
        return self.driver.read_point(f"bms_rack_{rack_id}", key)

    def rack_state(self, rack_id: int) -> BatteryRackState:
        keys = [
            "rack_state", "rack_operating_state", "rack_voltage", "rack_current", "rack_soc", "rack_soh",
            "rack_max_charge_power", "rack_max_discharge_power", "rack_max_charge_current", "rack_max_discharge_current",
            "positive_contactor_feedback", "negative_contactor_feedback",
            "positive_insulation_resistance", "negative_insulation_resistance",
        ]
        points: dict[str, dict[str, Any] | None] = {}
        errors: list[str] = []
        for key in keys:
            try:
                points[key] = self._read(rack_id, key)
            except Exception as error:  # one missing/failed point must not hide the full readiness picture
                points[key] = None
                errors.append(f"{key}: {error}")

        state_code = self._value(points["rack_state"])
        operating_code = self._value(points["rack_operating_state"])
        state_int = int(state_code) if state_code is not None else None
        operating_int = int(operating_code) if operating_code is not None else None
        state_label = LINEAGE_STATE_LABELS.get(state_int) if state_int is not None else None
        operating_label = LINEAGE_OPERATING_LABELS.get(operating_int) if operating_int is not None else None

        charge_allowed = state_int not in {None, 0x1111, 0x5555, 0xAAAA}
        discharge_allowed = state_int not in {None, 0x2222, 0x5555, 0xAAAA}
        blocking: list[str] = list(errors)
        if state_int == 0x1111:
            blocking.append("bms_no_charge")
        elif state_int == 0x2222:
            blocking.append("bms_no_discharge")
        elif state_int == 0x5555:
            blocking.append("bms_standby")
        elif state_int == 0xAAAA:
            blocking.append("bms_fault")
        elif state_int == 0xCCCC:
            # V05 labels Warn but does not state whether power must be blocked.
            # Preserve the warning without inventing a prohibition.
            blocking.append("bms_warning_vendor_policy_required")

        def num(key: str) -> float | None:
            value = self._value(points[key])
            return float(value) if value is not None else None

        def closed(key: str) -> bool | None:
            value = self._value(points[key])
            return bool(int(value)) if value is not None else None

        return BatteryRackState(
            rack_id=rack_id,
            online=not errors,
            state_code=state_int,
            state_label=state_label,
            operating_state_code=operating_int,
            operating_state_label=operating_label,
            voltage_v=num("rack_voltage"),
            current_a=num("rack_current"),
            soc_percent=num("rack_soc"),
            soh_percent=num("rack_soh"),
            max_charge_power_kw=num("rack_max_charge_power"),
            max_discharge_power_kw=num("rack_max_discharge_power"),
            max_charge_current_a=num("rack_max_charge_current"),
            max_discharge_current_a=num("rack_max_discharge_current"),
            positive_contactor_closed=closed("positive_contactor_feedback"),
            negative_contactor_closed=closed("negative_contactor_feedback"),
            positive_insulation_mohm=num("positive_insulation_resistance"),
            negative_insulation_mohm=num("negative_insulation_resistance"),
            charge_allowed=charge_allowed,
            discharge_allowed=discharge_allowed,
            blocking_reasons=tuple(blocking),
            raw={key: point for key, point in points.items() if point is not None},
        )

    def prepare_for_operation(self, rack_id: int) -> PreparationResult:
        state = self.rack_state(rack_id)
        contactors_ready = state.positive_contactor_closed is True and state.negative_contactor_closed is True
        if state.state_code == 0xAAAA:
            return PreparationResult(False, False, "blocked", "Lineage rack reports Fault", {"rack": state})
        if contactors_ready and state.voltage_v is not None:
            return PreparationResult(
                True,
                False,
                "ready",
                "Lineage BMS already reports both main contactors closed and rack voltage available.",
                {"rack": state},
            )
        return PreparationResult(
            False,
            False,
            "waiting_for_bms_automatic_precharge",
            "V05 exposes no normal EMS precharge command; wait for the vendor-approved BMS automatic startup/precharge sequence.",
            {"rack": state},
        )

    def disconnect(self, rack_id: int) -> PreparationResult:
        if not self.allow_forced_contactor_control:
            return PreparationResult(
                False,
                False,
                "capability_gated",
                "Forced Lineage contactor opening is disabled until vendor-safe sequencing is confirmed.",
                {"rack_id": rack_id},
            )
        asset_id = f"bms_rack_{rack_id}"
        positive = self.driver.write_point(asset_id, "positive_contactor_command", 2)
        negative = self.driver.write_point(asset_id, "negative_contactor_command", 2)
        return PreparationResult(
            True,
            True,
            "forced_open_requested",
            "EMS forced-open commands written to both Lineage main contactors.",
            {"positive": positive, "negative": negative},
        )

    def fault_reset(self) -> dict[str, Any]:
        return self.driver.write_point("bms_bank", "fault_reset", 1)
