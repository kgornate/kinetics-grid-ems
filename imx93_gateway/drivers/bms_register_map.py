"""
BMS / BCU Modbus TCP Register Map
Kinetics Grid EMS Gateway

Source workbook:
Kinetics Grid EMS BCU/BMS register analysis workbook
Sheet used: MVP Registers + Bitfield Details

Address convention:
- All addresses below are protocol/register offsets in hexadecimal form.
- For pymodbus read_holding_registers(address=...), pass these integer offsets directly,
  e.g. read_holding_registers(address=0x0210, count=42, device_id=1).
- If a simulator UI displays 4xxxx addresses, it may show these with a 40001-style offset.

Current sign convention:
- total_cur uses 0.1 A scaling and signed 16-bit decoding.
- Positive current should be treated as discharge, negative current as charge unless field validation says otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional


# -----------------------------------------------------------------------------
# Modbus TCP defaults for the PC simulator / BCU asset
# -----------------------------------------------------------------------------
BMS_ASSET_ID = "bms_1"
BMS_DEFAULT_HOST = "192.168.10.1"
BMS_DEFAULT_PORT = 502
BMS_DEFAULT_UNIT_ID = 1


# -----------------------------------------------------------------------------
# Register metadata model
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class RegisterDef:
    key: str
    address: int
    name: str
    category: str
    subcategory: str
    access: str = "R"
    data_format: str = "u16"       # u16 / s16
    scale: Optional[float] = None   # None means raw value
    unit: Optional[str] = None
    description: str = ""


# -----------------------------------------------------------------------------
# Core read blocks
# These are contiguous blocks from the workbook and should be efficient for polling.
# -----------------------------------------------------------------------------
READ_BLOCKS: Dict[str, Dict[str, int]] = {
    # Rack Signal: alarm + status block, 0x0010 to 0x001F inclusive
    "rack_signal_core": {"start": 0x0010, "count": 0x001F - 0x0010 + 1},
    # Rack Measure: core measurement block, 0x0210 to 0x0239 inclusive
    "rack_measure_core": {"start": 0x0210, "count": 0x0239 - 0x0210 + 1},
}


# -----------------------------------------------------------------------------
# Rack Signal registers: alarms + status
# -----------------------------------------------------------------------------
RACK_SIGNAL_REGISTERS: Dict[str, RegisterDef] = {
    "functional_safety_warn": RegisterDef(
        key="functional_safety_warn", address=0x0010,
        name="Functional Safety Warning", category="C6 Battery Alarms & Faults",
        subcategory="Functional Safety Faults", data_format="u16",
        description="Bitfield register for first-level functional safety faults."
    ),
    "bcu_external_fault_alarm": RegisterDef(
        key="bcu_external_fault_alarm", address=0x0011,
        name="BCU External Fault Alarm", category="C6 Battery Alarms & Faults",
        subcategory="Critical Faults", data_format="u16",
        description="Bitfield register for BCU/BMU external critical faults."
    ),
    "extern_critical_alarm": RegisterDef(
        key="extern_critical_alarm", address=0x0012,
        name="External Critical Alarm 1", category="C6 Battery Alarms & Faults",
        subcategory="Critical Faults", data_format="u16",
        description="Bitfield register for first-level voltage/current/temperature/insulation faults."
    ),
    "extern_alarm": RegisterDef(
        key="extern_alarm", address=0x0013,
        name="External Alarm 1", category="C6 Battery Alarms & Faults",
        subcategory="Second-Level Alarms", data_format="u16",
        description="Bitfield register for second-level voltage/current/temperature/insulation alarms."
    ),
    "extern_warn": RegisterDef(
        key="extern_warn", address=0x0014,
        name="External Warning 1", category="C6 Battery Alarms & Faults",
        subcategory="Third-Level Warnings", data_format="u16",
        description="Bitfield register for third-level warnings."
    ),
    "extern_critical_alarm2": RegisterDef(
        key="extern_critical_alarm2", address=0x0015,
        name="External Critical Alarm 2", category="C6 Battery Alarms & Faults",
        subcategory="Critical Faults", data_format="u16",
        description="Bitfield register for additional first-level rack/module faults."
    ),
    "extern_alarm2": RegisterDef(
        key="extern_alarm2", address=0x0016,
        name="External Alarm 2", category="C6 Battery Alarms & Faults",
        subcategory="Second-Level Alarms", data_format="u16",
        description="Bitfield register for additional second-level rack/module alarms."
    ),
    "extern_warn2": RegisterDef(
        key="extern_warn2", address=0x0017,
        name="External Warning 2", category="C6 Battery Alarms & Faults",
        subcategory="Third-Level Warnings", data_format="u16",
        description="Bitfield register for additional third-level rack/module warnings."
    ),
    "pre_power_stage": RegisterDef(
        key="pre_power_stage", address=0x0018,
        name="Pre-Power / Precharge Stage", category="C1 Battery System Status",
        subcategory="Precharge Status", data_format="u16",
        description="0=Idle, 1/2=Precharging, 3=Precharge success, 4=Precharge failed."
    ),
    "bcu_state": RegisterDef(
        key="bcu_state", address=0x0019,
        name="BCU System State", category="C1 Battery System Status",
        subcategory="System Operating Status", data_format="u16",
        description="0=Normal/Idle, 1=Charge forbidden, 2=Discharge forbidden, 3=Standby, 4=Stop/Shutdown."
    ),
    "heart_beat_num": RegisterDef(
        key="heart_beat_num", address=0x001A,
        name="Heartbeat Number", category="C1 Battery System Status",
        subcategory="Communication Heartbeat", data_format="u16",
        description="Heartbeat frame/counter, expected to increment periodically."
    ),
    "receive_cfg_state": RegisterDef(
        key="receive_cfg_state", address=0x001B,
        name="Receive Configuration State", category="C6 Battery Alarms & Faults",
        subcategory="Vendor Extension", data_format="u16",
        description="0=BMU/slave registration failed, 1=BMU/slave registration success."
    ),
    "pre_chg_fail_reason": RegisterDef(
        key="pre_chg_fail_reason", address=0x001C,
        name="Precharge Failure Reason", category="C6 Battery Alarms & Faults",
        subcategory="Vendor Extension", data_format="u16",
        description="Reserved/vendor-specific precharge failure reason."
    ),
    "current_state": RegisterDef(
        key="current_state", address=0x001D,
        name="Charge / Discharge State", category="C1 Battery System Status",
        subcategory="Charge / Discharge State", data_format="u16",
        description="0=Idle, 1=Discharge, 2=Charge."
    ),
    "full_or_empty_flag": RegisterDef(
        key="full_or_empty_flag", address=0x001E,
        name="Full or Empty Flag", category="C1 Battery System Status",
        subcategory="System Operating Status", data_format="u16",
        description="0=Full, 1=Empty, as per workbook. Field validation recommended."
    ),
    "bcu_contactor_state": RegisterDef(
        key="bcu_contactor_state", address=0x001F,
        name="BCU Contactor State", category="C1 Battery System Status",
        subcategory="Contactor / Operating Status", data_format="u16",
        description="Bitfield: positive relay, precharge relay, negative relay, disconnector feedback."
    ),
}


# -----------------------------------------------------------------------------
# Rack Measure registers: telemetry, health, safety
# -----------------------------------------------------------------------------
RACK_MEASURE_REGISTERS: Dict[str, RegisterDef] = {
    "max_cell_vol": RegisterDef("max_cell_vol", 0x0210, "Maximum Cell Voltage", "C2 Battery Electrical Measurements", "Cell Voltage Statistics", unit="mV"),
    "max_cell_vol_num": RegisterDef("max_cell_vol_num", 0x0211, "Maximum Cell Voltage Number", "C2 Battery Electrical Measurements", "Cell Voltage Statistics"),
    "max_vol_bmu_num": RegisterDef("max_vol_bmu_num", 0x0212, "Maximum Voltage BMU Number", "C2 Battery Electrical Measurements", "Cell Voltage Statistics"),
    "bmu_max_vol_num": RegisterDef("bmu_max_vol_num", 0x0213, "BMU Maximum Voltage Cell Number", "C2 Battery Electrical Measurements", "Cell Voltage Statistics"),
    "min_cell_vol": RegisterDef("min_cell_vol", 0x0214, "Minimum Cell Voltage", "C2 Battery Electrical Measurements", "Cell Voltage Statistics", unit="mV"),
    "min_cell_vol_num": RegisterDef("min_cell_vol_num", 0x0215, "Minimum Cell Voltage Number", "C2 Battery Electrical Measurements", "Cell Voltage Statistics"),
    "min_vol_bmu_num": RegisterDef("min_vol_bmu_num", 0x0216, "Minimum Voltage BMU Number", "C2 Battery Electrical Measurements", "Cell Voltage Statistics"),
    "bmu_min_vol_num": RegisterDef("bmu_min_vol_num", 0x0217, "BMU Minimum Voltage Cell Number", "C2 Battery Electrical Measurements", "Cell Voltage Statistics"),
    "max_cell_vol_diff": RegisterDef("max_cell_vol_diff", 0x0218, "Maximum Cell Voltage Difference", "C2 Battery Electrical Measurements", "Cell Voltage Statistics", unit="mV"),
    "ave_cell_vol": RegisterDef("ave_cell_vol", 0x0219, "Average Cell Voltage", "C2 Battery Electrical Measurements", "Cell Voltage Statistics", unit="mV"),

    "max_cell_temp": RegisterDef("max_cell_temp", 0x021A, "Maximum Cell Temperature", "C3 Battery Thermal Measurements", "Thermal Measurements", data_format="s16", scale=0.1, unit="degC"),
    "max_cell_temp_num": RegisterDef("max_cell_temp_num", 0x021B, "Maximum Cell Temperature Number", "C3 Battery Thermal Measurements", "Thermal Measurements"),
    "max_temp_bmu_num": RegisterDef("max_temp_bmu_num", 0x021C, "Maximum Temperature BMU Number", "C3 Battery Thermal Measurements", "Thermal Measurements"),
    "bmu_max_temp_num": RegisterDef("bmu_max_temp_num", 0x021D, "BMU Maximum Temperature Number", "C3 Battery Thermal Measurements", "Thermal Measurements"),
    "min_cell_temp": RegisterDef("min_cell_temp", 0x021E, "Minimum Cell Temperature", "C3 Battery Thermal Measurements", "Thermal Measurements", data_format="s16", scale=0.1, unit="degC"),
    "min_cell_temp_num": RegisterDef("min_cell_temp_num", 0x021F, "Minimum Cell Temperature Number", "C3 Battery Thermal Measurements", "Thermal Measurements"),
    "min_temp_bmu_num": RegisterDef("min_temp_bmu_num", 0x0220, "Minimum Temperature BMU Number", "C3 Battery Thermal Measurements", "Thermal Measurements"),
    "bmu_min_temp_num": RegisterDef("bmu_min_temp_num", 0x0221, "BMU Minimum Temperature Number", "C3 Battery Thermal Measurements", "Thermal Measurements"),
    "rack_ave_temp": RegisterDef("rack_ave_temp", 0x0222, "Rack Average Temperature", "C3 Battery Thermal Measurements", "Thermal Measurements", data_format="s16", scale=0.1, unit="degC"),
    "max_polarity_temp": RegisterDef("max_polarity_temp", 0x0223, "Maximum Terminal Temperature", "C3 Battery Thermal Measurements", "Thermal Measurements", data_format="s16", scale=0.1, unit="degC"),
    "max_polarity_num": RegisterDef("max_polarity_num", 0x0224, "Maximum Terminal Number", "C2 Battery Electrical Measurements", "Rack Measurements"),

    "max_allowed_chg_cur": RegisterDef("max_allowed_chg_cur", 0x0225, "Maximum Allowed Charge Current", "C2 Battery Electrical Measurements", "Charge/Discharge Limits", scale=0.1, unit="A"),
    "max_allowed_dchg_cur": RegisterDef("max_allowed_dchg_cur", 0x0226, "Maximum Allowed Discharge Current", "C2 Battery Electrical Measurements", "Charge/Discharge Limits", scale=0.1, unit="A"),
    "display_soc": RegisterDef("display_soc", 0x0227, "Display SOC", "C4 Battery Health & Capacity", "SOC/SOH", scale=0.1, unit="%", description="Workbook unit is per-mille; converted to percent by value * 0.1."),
    "soh": RegisterDef("soh", 0x0228, "SOH", "C4 Battery Health & Capacity", "SOC/SOH", scale=0.1, unit="%", description="Workbook unit is per-mille; converted to percent by value * 0.1."),
    "max_bat_temp_diff": RegisterDef("max_bat_temp_diff", 0x0229, "Maximum Battery Temperature Difference", "C3 Battery Thermal Measurements", "Thermal Measurements", scale=0.1, unit="degC"),
    "max_bat_temp_rise": RegisterDef("max_bat_temp_rise", 0x022A, "Maximum Battery Temperature Rise", "C3 Battery Thermal Measurements", "Thermal Measurements", scale=0.1, unit="degC"),
    "max_bat_temp_rise_bmu_num": RegisterDef("max_bat_temp_rise_bmu_num", 0x022B, "Maximum Battery Temperature Rise BMU Number", "C3 Battery Thermal Measurements", "Thermal Measurements"),
    "max_bat_temp_rise_num_in_bmu": RegisterDef("max_bat_temp_rise_num_in_bmu", 0x022C, "Maximum Battery Temperature Rise Number In BMU", "C3 Battery Thermal Measurements", "Thermal Measurements"),
    "max_bat_temp_rise_num_in_bcu": RegisterDef("max_bat_temp_rise_num_in_bcu", 0x022D, "Maximum Battery Temperature Rise Number In BCU", "C3 Battery Thermal Measurements", "Thermal Measurements"),
    "rack_inner_soc": RegisterDef("rack_inner_soc", 0x022E, "Rack Internal SOC", "C4 Battery Health & Capacity", "SOC/SOH", scale=0.1, unit="%", description="Workbook unit is per-mille; converted to percent by value * 0.1."),

    "pre_chg_vol": RegisterDef("pre_chg_vol", 0x022F, "Precharge Voltage", "C2 Battery Electrical Measurements", "Electrical Measurements", data_format="s16", scale=0.1, unit="V"),
    "bmu_total_vol": RegisterDef("bmu_total_vol", 0x0230, "BMU Total Voltage", "C2 Battery Electrical Measurements", "Electrical Measurements", data_format="s16", scale=0.1, unit="V"),
    "total_vol": RegisterDef("total_vol", 0x0231, "Total Rack Voltage", "C2 Battery Electrical Measurements", "Electrical Measurements", data_format="s16", scale=0.1, unit="V"),
    "total_cur": RegisterDef("total_cur", 0x0232, "Total Rack Current", "C2 Battery Electrical Measurements", "Electrical Measurements", data_format="s16", scale=0.1, unit="A"),
    "ncon_total_vol": RegisterDef("ncon_total_vol", 0x0233, "NCON Total Voltage", "C2 Battery Electrical Measurements", "Electrical Measurements", data_format="s16", scale=0.1, unit="V"),
    "shunt_current": RegisterDef("shunt_current", 0x0234, "Shunt Current", "C2 Battery Electrical Measurements", "Electrical Measurements", data_format="s16", scale=0.1, unit="A"),
    "can_hall_sample_cur_ori_value": RegisterDef("can_hall_sample_cur_ori_value", 0x0235, "CAN Hall Sample Current Original Value", "C2 Battery Electrical Measurements", "Electrical Measurements", data_format="s16", scale=0.1, unit="A"),
    "cur_vol_hall_sam_cur_ori_value": RegisterDef("cur_vol_hall_sam_cur_ori_value", 0x0236, "Current/Voltage Hall Sample Current Original Value", "C2 Battery Electrical Measurements", "Electrical Measurements", data_format="s16", scale=0.1, unit="A"),

    "ir": RegisterDef("ir", 0x0237, "Insulation Resistance", "C5 Battery Safety & Protection", "Insulation & Safety", unit="kOhm"),
    "positive_ir": RegisterDef("positive_ir", 0x0238, "Positive Insulation Resistance", "C5 Battery Safety & Protection", "Insulation & Safety", unit="kOhm"),
    "negative_ir": RegisterDef("negative_ir", 0x0239, "Negative Insulation Resistance", "C5 Battery Safety & Protection", "Insulation & Safety", unit="kOhm"),
}


# -----------------------------------------------------------------------------
# Control registers
# -----------------------------------------------------------------------------
CONTROL_REGISTERS: Dict[str, RegisterDef] = {
    "start_insulation_sampling": RegisterDef(
        key="start_insulation_sampling", address=0x0401,
        name="Start Insulation Sampling", category="C7 Battery Control Commands",
        subcategory="Insulation Test Control", access="R/W", data_format="u16",
        description="Write 1 to start/reset insulation sampling; other value = no action."
    ),
    "start_precharge": RegisterDef(
        key="start_precharge", address=0x0402,
        name="Start Precharge Operation", category="C7 Battery Control Commands",
        subcategory="Precharge Control", access="R/W", data_format="u16",
        description="Write 0x01 to start precharge; other value = stop/open precharge path."
    ),
    "bcu_reset": RegisterDef(
        key="bcu_reset", address=0x0403,
        name="BCU Reset", category="C7 Battery Control Commands",
        subcategory="Commissioning / Reset Control", access="R/W", data_format="u16",
        description="Write 0x01 to reset BCU; other value = no reset."
    ),
    "fan_switch": RegisterDef(
        key="fan_switch", address=0x0406,
        name="Fan Force Control", category="C7 Battery Control Commands",
        subcategory="Fan Control", access="R/W", data_format="u16",
        description="Write 1=Fan ON, 2=Fan OFF. 0 may be used by EMS as auto/no-force if validated."
    ),
}

CONTROL_VALUES: Dict[str, Dict[str, int]] = {
    "start_insulation_sampling": {"start": 1, "no_action": 0},
    "start_precharge": {"start": 1, "stop": 0},
    "bcu_reset": {"reset": 1, "no_action": 0},
    "fan_switch": {"auto": 0, "on": 1, "off": 2},
}


# -----------------------------------------------------------------------------
# Enumerations / decoded states
# -----------------------------------------------------------------------------
PRE_POWER_STAGE_MAP = {
    0: "idle",
    1: "precharging",
    2: "precharging",
    3: "precharge_success",
    4: "precharge_failed",
}

BCU_STATE_MAP = {
    0: "normal_idle",
    1: "charge_forbidden",
    2: "discharge_forbidden",
    3: "standby",
    4: "stop_shutdown",
}

CURRENT_STATE_MAP = {
    0: "idle",
    1: "discharge",
    2: "charge",
}

FULL_OR_EMPTY_FLAG_MAP = {
    0: "full",
    1: "empty",
}

RECEIVE_CFG_STATE_MAP = {
    0: "registration_failed",
    1: "registration_success",
}


# -----------------------------------------------------------------------------
# Bitfield definitions
# Only active bits should be reported as alarms/status flags by the driver.
# -----------------------------------------------------------------------------
BITFIELDS: Dict[str, Dict[int, str]] = {
    "functional_safety_warn": {
        0: "total_voltage_difference",
        1: "insulation_low",
        2: "battery_voltage_high",
        3: "battery_temperature_high",
        4: "battery_voltage_update_fault",
        5: "terminal_temperature_high",
        6: "current_high",
        7: "insulation_error",
        8: "ntc_fault",
        9: "terminal_temperature_sensor_fault",
        10: "battery_temperature_sensor_fault",
        11: "voltage_sample_fault",
        12: "sample_chip_fault",
        13: "current_sample_fault",
        14: "battery_voltage_low",
        15: "vhg_current_high",
    },
    "bcu_external_fault_alarm": {
        0: "bmu_self_check_fault",
        1: "bcu_self_check_fault",
        2: "fuse_fault",
        3: "main_positive_contactor_fault",
        4: "main_negative_contactor_fault",
        5: "precharge_contactor_fault",
        6: "bmu_communication_fault",
        7: "power_outage_fault",
        8: "hvbox_fault",
        9: "hvbox_communication_fault",
        10: "hvbox_temperature_fault",
        11: "charge_discharge_circuit_fault",
        12: "safety_alarm",
        13: "pcs_communication_fault",
        14: "reserved_14",
        15: "reserved_15",
    },
    "extern_critical_alarm": {
        0: "rack_voltage_high",
        1: "rack_voltage_low",
        2: "cell_voltage_high",
        3: "cell_voltage_low",
        4: "charge_current_high",
        5: "discharge_current_high",
        6: "discharge_temperature_high",
        7: "discharge_temperature_low",
        8: "charge_temperature_high",
        9: "charge_temperature_low",
        10: "insulation_low",
        11: "terminal_temperature_high",
        12: "hvbox_temperature_high",
        13: "cell_voltage_difference_high",
        14: "cell_temperature_difference_high",
    },
    "extern_alarm": {
        0: "rack_voltage_high",
        1: "rack_voltage_low",
        2: "cell_voltage_high",
        3: "cell_voltage_low",
        4: "charge_current_high",
        5: "discharge_current_high",
        6: "discharge_temperature_high",
        7: "discharge_temperature_low",
        8: "charge_temperature_high",
        9: "charge_temperature_low",
        10: "insulation_low",
        11: "terminal_temperature_high",
        12: "hvbox_temperature_high",
        13: "cell_voltage_difference_high",
        14: "cell_temperature_difference_high",
    },
    "extern_warn": {
        0: "rack_voltage_high",
        1: "rack_voltage_low",
        2: "cell_voltage_high",
        3: "cell_voltage_low",
        4: "charge_current_high",
        5: "discharge_current_high",
        6: "discharge_temperature_high",
        7: "discharge_temperature_low",
        8: "charge_temperature_high",
        9: "charge_temperature_low",
        10: "insulation_low",
        11: "terminal_temperature_high",
        12: "hvbox_temperature_high",
        13: "cell_voltage_difference_high",
        14: "cell_temperature_difference_high",
        15: "soc_behind_low",
    },
    "extern_critical_alarm2": {
        0: "total_voltage_battery_voltage_difference_high",
        1: "module_voltage_over",
        2: "module_voltage_low",
        3: "battery_high_temperature_rise_alarm",
        4: "module_voltage_difference_over",
    },
    "extern_alarm2": {
        0: "total_voltage_battery_voltage_difference_high",
        1: "module_voltage_over",
        2: "module_voltage_low",
        3: "battery_high_temperature_rise_alarm",
        4: "module_voltage_difference_over",
    },
    "extern_warn2": {
        0: "total_voltage_battery_voltage_difference_high",
        1: "module_voltage_over",
        2: "module_voltage_low",
        3: "battery_high_temperature_rise_alarm",
        4: "module_voltage_difference_over",
    },
    "bcu_contactor_state": {
        0: "positive_relay_closed",
        1: "precharge_relay_closed",
        2: "negative_relay_closed",
        3: "disconnector_feedback_closed",
    },
}

ALARM_REGISTER_KEYS = [
    "functional_safety_warn",
    "bcu_external_fault_alarm",
    "extern_critical_alarm",
    "extern_alarm",
    "extern_warn",
    "extern_critical_alarm2",
    "extern_alarm2",
    "extern_warn2",
]

STATUS_REGISTER_KEYS = [
    "pre_power_stage",
    "bcu_state",
    "heart_beat_num",
    "receive_cfg_state",
    "pre_chg_fail_reason",
    "current_state",
    "full_or_empty_flag",
    "bcu_contactor_state",
]

CORE_TELEMETRY_KEYS = [
    "display_soc",
    "soh",
    "rack_inner_soc",
    "total_vol",
    "total_cur",
    "max_allowed_chg_cur",
    "max_allowed_dchg_cur",
    "max_cell_vol",
    "min_cell_vol",
    "max_cell_vol_diff",
    "ave_cell_vol",
    "max_cell_temp",
    "min_cell_temp",
    "rack_ave_temp",
    "max_bat_temp_diff",
    "ir",
    "positive_ir",
    "negative_ir",
]

ALL_CORE_REGISTERS: Dict[str, RegisterDef] = {
    **RACK_SIGNAL_REGISTERS,
    **RACK_MEASURE_REGISTERS,
    **CONTROL_REGISTERS,
}


# -----------------------------------------------------------------------------
# Utility functions used by simulator, CLI and driver
# -----------------------------------------------------------------------------
def decode_s16(value: int) -> int:
    """Convert unsigned 16-bit register value to signed int16."""
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def encode_s16(value: int) -> int:
    """Convert signed int16 value to Modbus unsigned 16-bit register representation."""
    if value < 0:
        value = 0x10000 + value
    return value & 0xFFFF


def apply_scale(raw_value: int, reg: RegisterDef) -> float | int:
    value = decode_s16(raw_value) if reg.data_format.lower() in {"s16", "int16"} else raw_value
    if reg.scale is None:
        return value
    return value * reg.scale


def decode_bitfield(value: int, key: str) -> List[str]:
    """Return list of active bit names for a bitfield register key."""
    bit_defs = BITFIELDS.get(key, {})
    return [name for bit, name in bit_defs.items() if value & (1 << bit)]


def decode_status_value(key: str, value: int) -> str | int:
    if key == "pre_power_stage":
        return PRE_POWER_STAGE_MAP.get(value, f"unknown_{value}")
    if key == "bcu_state":
        return BCU_STATE_MAP.get(value, f"unknown_{value}")
    if key == "current_state":
        return CURRENT_STATE_MAP.get(value, f"unknown_{value}")
    if key == "full_or_empty_flag":
        return FULL_OR_EMPTY_FLAG_MAP.get(value, f"unknown_{value}")
    if key == "receive_cfg_state":
        return RECEIVE_CFG_STATE_MAP.get(value, f"unknown_{value}")
    return value


def register_offset(address: int, block_start: int) -> int:
    """Get zero-based index of address within a read block."""
    return address - block_start


def decode_block(register_values: List[int], block_name: str) -> Dict[str, Any]:
    """Decode a raw contiguous Modbus register block into EMS key/value pairs."""
    if block_name not in READ_BLOCKS:
        raise ValueError(f"Unknown BMS read block: {block_name}")

    start = READ_BLOCKS[block_name]["start"]
    decoded: Dict[str, Any] = {}

    if block_name == "rack_signal_core":
        reg_defs = RACK_SIGNAL_REGISTERS
    elif block_name == "rack_measure_core":
        reg_defs = RACK_MEASURE_REGISTERS
    else:
        reg_defs = {}

    for key, reg in reg_defs.items():
        idx = register_offset(reg.address, start)
        if 0 <= idx < len(register_values):
            raw = register_values[idx]
            if key in BITFIELDS:
                decoded[key] = {
                    "raw": raw,
                    "active": decode_bitfield(raw, key),
                }
            elif key in STATUS_REGISTER_KEYS:
                decoded[key] = {
                    "raw": raw,
                    "decoded": decode_status_value(key, raw),
                }
            else:
                decoded[key] = apply_scale(raw, reg)
    return decoded


def build_core_telemetry(measurements: Mapping[str, Any], status: Mapping[str, Any]) -> Dict[str, Any]:
    """Build EMS-friendly telemetry payload from decoded blocks."""
    voltage = measurements.get("total_vol")
    current = measurements.get("total_cur")
    power_kw = None
    if isinstance(voltage, (int, float)) and isinstance(current, (int, float)):
        power_kw = round((voltage * current) / 1000.0, 3)

    contactor = status.get("bcu_contactor_state", {})
    contactor_active = contactor.get("active", []) if isinstance(contactor, dict) else []

    return {
        "asset_id": BMS_ASSET_ID,
        "soc_percent": measurements.get("display_soc"),
        "soh_percent": measurements.get("soh"),
        "rack_inner_soc_percent": measurements.get("rack_inner_soc"),
        "rack_voltage_v": voltage,
        "rack_current_a": current,
        "power_kw": power_kw,
        "max_allowed_charge_current_a": measurements.get("max_allowed_chg_cur"),
        "max_allowed_discharge_current_a": measurements.get("max_allowed_dchg_cur"),
        "max_cell_voltage_mv": measurements.get("max_cell_vol"),
        "min_cell_voltage_mv": measurements.get("min_cell_vol"),
        "avg_cell_voltage_mv": measurements.get("ave_cell_vol"),
        "cell_voltage_diff_mv": measurements.get("max_cell_vol_diff"),
        "max_cell_temp_c": measurements.get("max_cell_temp"),
        "min_cell_temp_c": measurements.get("min_cell_temp"),
        "avg_temp_c": measurements.get("rack_ave_temp"),
        "max_temp_diff_c": measurements.get("max_bat_temp_diff"),
        "insulation_resistance_kohm": measurements.get("ir"),
        "positive_insulation_resistance_kohm": measurements.get("positive_ir"),
        "negative_insulation_resistance_kohm": measurements.get("negative_ir"),
        "precharge_stage": status.get("pre_power_stage", {}).get("decoded") if isinstance(status.get("pre_power_stage"), dict) else None,
        "bcu_state": status.get("bcu_state", {}).get("decoded") if isinstance(status.get("bcu_state"), dict) else None,
        "current_state": status.get("current_state", {}).get("decoded") if isinstance(status.get("current_state"), dict) else None,
        "heartbeat": status.get("heart_beat_num", {}).get("raw") if isinstance(status.get("heart_beat_num"), dict) else None,
        "contactor_active_flags": contactor_active,
        "positive_contactor_closed": "positive_relay_closed" in contactor_active,
        "precharge_contactor_closed": "precharge_relay_closed" in contactor_active,
        "negative_contactor_closed": "negative_relay_closed" in contactor_active,
    }


def collect_active_alarms(decoded_status_block: Mapping[str, Any]) -> List[str]:
    """Flatten active alarm bitfields into human-readable alarm keys."""
    alarms: List[str] = []
    for register_key in ALARM_REGISTER_KEYS:
        entry = decoded_status_block.get(register_key)
        if isinstance(entry, Mapping):
            for alarm in entry.get("active", []):
                if not alarm.startswith("reserved"):
                    alarms.append(f"{register_key}.{alarm}")
    return alarms


__all__ = [
    "BMS_ASSET_ID", "BMS_DEFAULT_HOST", "BMS_DEFAULT_PORT", "BMS_DEFAULT_UNIT_ID",
    "RegisterDef", "READ_BLOCKS", "RACK_SIGNAL_REGISTERS", "RACK_MEASURE_REGISTERS",
    "CONTROL_REGISTERS", "CONTROL_VALUES", "BITFIELDS", "ALARM_REGISTER_KEYS",
    "STATUS_REGISTER_KEYS", "CORE_TELEMETRY_KEYS", "ALL_CORE_REGISTERS",
    "decode_s16", "encode_s16", "apply_scale", "decode_bitfield", "decode_status_value",
    "decode_block", "build_core_telemetry", "collect_active_alarms",
]
