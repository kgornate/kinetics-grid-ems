from __future__ import annotations

from typing import Any

from app.core.config import GatewayConfig

RELEASE_VERSION = "0.9.0-software-complete-rc"
ARCHITECTURE_BASELINE = "kinetics-derived-ornate-ems-gateway-v1"


def _gate(name: str, validated: bool, *, critical: bool = True, note: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "validated": bool(validated),
        "status": "validated" if validated else "pending_field_validation",
        "critical_for_hardware_control": critical,
        "note": note,
    }


def platform_readiness(config: GatewayConfig) -> dict[str, Any]:
    """Return software-completeness and field-commissioning gates.

    The Lineage V05 and Elecod V2.7.0 source documents support the register
    catalog and control implementation, but several device behaviours are not
    specified unambiguously.  Those points remain explicit commissioning gates
    rather than hidden assumptions.
    """

    lineage_elecod = (
        config.bms.vendor.strip().lower() == "lineage"
        and config.pcs.vendor.strip().lower() == "elecod"
    )

    gates: list[dict[str, Any]] = []
    if lineage_elecod:
        gates.extend(
            [
                _gate(
                    "Lineage Modbus register addressing/offset",
                    config.bms.addressing_validated,
                    note="Confirm known system/rack values against the V05 decimal addresses.",
                ),
                _gate(
                    "Lineage FLOAT32 word order",
                    config.bms.float_word_order_validated,
                    note="V05 states FLOAT32 but does not define 32-bit word order.",
                ),
                _gate(
                    "Lineage rack/system current sign",
                    config.bms.current_sign_validated,
                    note="V05 does not define positive/negative current direction.",
                ),
                _gate(
                    "Lineage automatic precharge/readiness ownership",
                    config.bms.automatic_precharge_validated,
                    note=(
                        "V05 exposes main-contactor feedback and precharge faults but no normal EMS precharge command; "
                        "the gateway waits for BMS automatic readiness and never invents a forced-close precharge sequence."
                    ),
                ),
                _gate(
                    "Lineage forced battery disconnect sequence",
                    config.bms.forced_disconnect_sequence_validated,
                    critical=config.control_sequence.allow_forced_bms_disconnect,
                    note=(
                        "Only required when EMS-forced contactor opening is intentionally enabled. "
                        "It is disabled by default."
                    ),
                ),
                _gate(
                    "Elecod Modbus register addressing/offset",
                    config.pcs.addressing_validated,
                    note="Confirm telemetry and status against V2.7.0 before writes.",
                ),
                _gate(
                    "Elecod active-power sign convention",
                    config.pcs.power_sign_validated,
                    note="Register map strongly implies +P discharge / -P charge; commissioning must confirm it.",
                ),
                _gate(
                    "Elecod start/stop write semantics",
                    config.pcs.start_stop_validated,
                    note="V2.7.0 documents 5050 while FC05/FC06 wording is inconsistent; driver defaults to FC06.",
                ),
                _gate(
                    "Elecod readiness/status interpretation",
                    config.pcs.ready_status_validated,
                    note="Confirm 2057 relay/run/fault state behaviour during real startup.",
                ),
            ]
        )

    critical_pending = [
        item["name"] for item in gates if item["critical_for_hardware_control"] and not item["validated"]
    ]
    write_gates = {
        "gateway_mode": config.mode,
        "bms_write_enabled": config.bms.write_enabled,
        "pcs_write_enabled": config.pcs.write_enabled,
        "pair_control_enabled": config.control_sequence.enabled,
        "automatic_sequence_enabled": config.control_sequence.allow_full_automatic_sequence,
        "power_sign_validated": config.pcs.power_sign_validated,
    }

    hardware_control_armed = (
        lineage_elecod
        and config.mode == "control_enabled"
        and config.bms.write_enabled
        and config.pcs.write_enabled
        and config.control_sequence.enabled
        and not critical_pending
    )
    automatic_control_armed = hardware_control_armed and config.control_sequence.allow_full_automatic_sequence

    return {
        "release": RELEASE_VERSION,
        "architecture_baseline": ARCHITECTURE_BASELINE,
        "software_status": "software_complete_field_validation_pending" if lineage_elecod else "legacy_supported",
        "software_scope": {
            "complete_source_tree": True,
            "legacy_kinetics_support_retained": True,
            "lineage_bms_read_path": True,
            "elecod_pcs_read_path": True,
            "normalized_asset_model": True,
            "pair_control_state_machine": True,
            "staged_control_api": True,
            "automatic_charge_discharge_sequence": True,
            "dynamic_bms_power_limiting": True,
            "runtime_safety_monitor": True,
            "safe_stop": True,
            "alarms_history_audit": True,
            "software_in_loop_config": "configs/elecod_lineage_4pair_sil.json",
        },
        "field_validation": {
            "required": lineage_elecod,
            "complete": lineage_elecod and not critical_pending,
            "critical_pending": critical_pending,
            "gates": gates,
            "bms_commissioning_status": config.bms.commissioning_status,
            "pcs_commissioning_status": config.pcs.commissioning_status,
        },
        "write_gates": write_gates,
        "hardware_control_armed": hardware_control_armed,
        "automatic_control_armed": automatic_control_armed,
        "safety_policy": {
            "lineage_warning_operation_allowed": config.control_sequence.allow_bms_warning_operation,
            "forced_bms_disconnect_allowed": config.control_sequence.allow_forced_bms_disconnect,
            "direct_elecod_critical_writes_via_generic_api": False,
            "control_path": "pair-control API through vendor adapters",
        },
    }
