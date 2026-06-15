#!/usr/bin/env python3
"""
Njoy / Enjoy 125kW PCS Modbus TCP Profile

This file contains vendor-specific register mapping and scaling.

Important protocol points:
- EMS acts as Modbus TCP client.
- PCS acts as Modbus TCP server.
- Read register function code: 0x03.
- Write register function codes: 0x06 and 0x10.
- Positive active power means discharge.
- Negative active power means charge.
"""

from typing import Dict, Any, List

from drivers.pcs_modbus_tcp_driver import PcsModbusTcpDriver


VENDOR_NAME = "njoy_125kw"

DEFAULT_HOST = "192.168.1.200"
DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 1


# -----------------------------
# Telemetry holding registers
# -----------------------------
REG_OUTPUT_AB_LINE_VOLTAGE = 0x6020
REG_OUTPUT_BC_LINE_VOLTAGE = 0x6021
REG_OUTPUT_CA_LINE_VOLTAGE = 0x6022

REG_OUTPUT_PHASE_A_VOLTAGE = 0x6023
REG_OUTPUT_PHASE_B_VOLTAGE = 0x6024
REG_OUTPUT_PHASE_C_VOLTAGE = 0x6025

REG_OUTPUT_PHASE_A_CURRENT = 0x6026
REG_OUTPUT_PHASE_B_CURRENT = 0x6027
REG_OUTPUT_PHASE_C_CURRENT = 0x6028

REG_GRID_FREQUENCY = 0x602C

REG_TOTAL_AC_ACTIVE_POWER = 0x6039
REG_TOTAL_AC_REACTIVE_POWER = 0x603A
REG_TOTAL_AC_APPARENT_POWER = 0x603B
REG_AC_POWER_FACTOR = 0x603C

REG_BUS_VOLTAGE = 0x6050
REG_BATTERY_VOLTAGE = 0x6053
REG_BATTERY_CURRENT = 0x6054
REG_DC_POWER = 0x6055
REG_DC_TOTAL_CURRENT = 0x6056

REG_OPERATING_STATUS = 0x6057
REG_IGBT_TEMPERATURE = 0x6058
REG_AMBIENT_TEMPERATURE = 0x6059
REG_INDUCTANCE_TEMPERATURE = 0x605A
REG_CURRENT_CHARGE_DISCHARGE_MODE = 0x605B
REG_GRID_OFFGRID_STATUS = 0x605C


# -----------------------------
# Control holding registers
# -----------------------------
REG_POWER_ON_OFF_COMMAND = 0x0291
REG_ACTIVE_POWER_SETTING = 0x500E
REG_REACTIVE_POWER_SETTING = 0x500F
REG_FAULT_RESET_COMMAND = 0x5064
REG_HEARTBEAT = 0x508E


# -----------------------------
# Detailed fault word registers
# -----------------------------
REG_HARDWARE_FAULT_WORD_1 = 0x1700
REG_HARDWARE_FAULT_WORD_2 = 0x1701
REG_GRID_FAULT_WORD = 0x1702
REG_BUS_FAULT_WORD = 0x1703
REG_AC_CAPACITOR_FAULT_WORD = 0x1704
REG_SYSTEM_FAULT_WORD = 0x1705
REG_SWITCH_FAULT_WORD = 0x1706
REG_OTHER_FAULT_WORD = 0x1707


FAULT_WORD_DEFINITIONS = {
    "hardware_fault_word_1": {
        0: "EPO fault",
        1: "IGBT OCP fault",
        2: "Bus hardware overvoltage fault",
        4: "Power module wave-by-wave current limiting fault",
        5: "Balance module wave-by-wave current limiting fault",
    },
    "hardware_fault_word_2": {
        0: "24V power supply fault",
        1: "Fan failure",
        2: "Connection fault",
        6: "External input dry contact 3 fault",
        7: "Inductor overtemperature fault flag",
        8: "Power module overtemperature fault",
        9: "Balance module overtemperature fault",
        10: "15V power supply fault",
        11: "System fire alarm fault",
        12: "External input dry contact 1 fault",
        13: "External input dry contact 2 fault",
        14: "Ambient temperature over-temperature fault",
        15: "Dry contact over-temperature fault",
    },
    "grid_fault_word": {
        0: "Phase A grid overvoltage fault",
        1: "Phase B grid overvoltage fault",
        2: "Phase C grid overvoltage fault",
        3: "Phase A grid undervoltage fault",
        4: "Phase B grid undervoltage fault",
        5: "Phase C grid undervoltage fault",
        6: "Grid overfrequency fault",
        7: "Grid underfrequency fault",
        8: "Grid phase sequence error fault",
        9: "Phase A software overcurrent fault",
        10: "Phase B software overcurrent fault",
        11: "Phase C software overcurrent fault",
        12: "Grid voltage imbalance fault",
        13: "Grid current imbalance fault",
        14: "Grid phase loss fault",
        15: "N-wire overcurrent fault",
    },
    "bus_fault_word": {
        0: "Precharge bus overvoltage fault",
        1: "Precharge bus undervoltage fault",
        4: "Operating bus overvoltage fault",
        5: "Operating bus undervoltage fault",
        6: "Positive/negative bus imbalance fault",
        7: "Battery undervoltage fault",
        9: "Battery overvoltage fault",
        10: "DC precharge overcurrent fault",
        11: "DC overcurrent fault",
        12: "Balancing module software overcurrent fault",
        15: "Battery reverse connection fault",
    },
    "ac_capacitor_fault_word": {
        0: "Precharge timeout fault",
        1: "Precharge Phase A overcurrent fault",
        2: "Precharge Phase B overcurrent fault",
        3: "Precharge Phase C overcurrent fault",
        6: "Leakage current overcurrent fault",
        7: "DC component current limit fault",
        8: "Power mismatch fault",
    },
    "system_fault_word": {
        0: "Control board RAM fault",
        1: "Control board EEPROM fault",
        2: "AD zero drift fault",
        3: "Background communication protocol fault",
        4: "CAN communication protocol fault",
        5: "CPLD communication protocol failure",
        6: "DataLog data fault",
        8: "Insulation detection fault",
        9: "Software/Firmware mismatch fault",
        11: "BMS battery status fault",
        12: "STS communication fault",
        13: "BMS communication fault",
        14: "Slave CAN communication failure in parallel system",
        15: "EMS communication fault",
    },
    "switch_fault_word": {
        0: "Precharge relay closure fault",
        1: "Precharge relay open fault",
        2: "Precharge relay closed state fault",
        3: "Precharge relay open state fault",
        4: "Main relay closed fault",
        5: "Main relay open fault",
        6: "Main relay closed state fault",
        7: "Main relay open state fault",
        8: "AC main relay sticking fault - contact manufacturer immediately",
        9: "DC relay open circuit fault - contact manufacturer immediately",
        10: "AC main relay open circuit fault - contact manufacturer immediately",
    },
    "other_fault_word": {
        0: "Inverter voltage phase A overvoltage fault",
        1: "Inverter voltage phase B overvoltage fault",
        2: "Inverter voltage phase C overvoltage fault",
        3: "Grid islanding fault",
        5: "System resonance fault",
        6: "Software overvoltage/overcurrent fault",
        8: "High voltage ride-through timeout fault",
        9: "Inverter voltage phase A undervoltage fault",
        10: "Inverter voltage phase B undervoltage fault",
        11: "Inverter voltage phase C undervoltage fault",
        12: "Off-grid no synchronization signal fault",
        14: "Off-grid output short-circuit fault",
        15: "Low voltage ride-through timeout fault",
    },
}


def raw_to_s16(raw: int) -> int:
    return PcsModbusTcpDriver.to_s16(raw)


def kw_to_raw(power_kw: float) -> int:
    """
    Njoy/Enjoy convention:
    +ve power = discharge
    -ve power = charge

    Scaling:
    kW x 10

    Example:
    +20.0 kW discharge -> +200
    -20.0 kW charge    -> -200
    """
    return int(round(power_kw * 10))


def kvar_to_raw(reactive_power_kvar: float) -> int:
    """
    Scaling:
    kvar x 10
    """
    return int(round(reactive_power_kvar * 10))


def decode_operating_status(raw: int) -> str:
    """
    Operating Status 0x6057 bit interpretation.

    Important bits:
    - all 0: shutdown
    - bit0 + bit1: powering on
    - bit0 + bit2: standby
    - bit0 + bit3: running in off-grid / DC voltage source mode
    - bit0 + bit8: running in grid-connected mode
    - bit6: fault
    """
    value = raw & 0xFFFF

    if value == 0:
        return "shutdown"

    if value & (1 << 6):
        return "fault"

    if (value & (1 << 0)) and (value & (1 << 8)):
        return "running_grid_connected"

    if (value & (1 << 0)) and (value & (1 << 3)):
        return "running_off_grid"

    if (value & (1 << 0)) and (value & (1 << 2)):
        return "standby"

    if (value & (1 << 0)) and (value & (1 << 1)):
        return "powering_on"

    return f"unknown_0x{value:04X}"


def decode_grid_offgrid_status(raw: int) -> str:
    mapping = {
        0: "shutdown",
        1: "powering_up",
        2: "standby",
        3: "off_grid_operation",
        4: "grid_connected_operation",
        5: "fault",
        6: "under_commissioning",
    }
    return mapping.get(raw, f"unknown_{raw}")


def decode_fault_word(raw: int, definitions: Dict[int, str]) -> List[str]:
    """Return active fault descriptions from a 16-bit fault word."""
    value = raw & 0xFFFF
    faults: List[str] = []
    for bit, description in definitions.items():
        if value & (1 << bit):
            faults.append(description)
    return faults


def decode_fault_words(fault_words_raw: Dict[str, int]) -> Dict[str, List[str]]:
    """Decode all NJOY/Enjoy PCS detailed fault-word categories."""
    decoded: Dict[str, List[str]] = {}
    for word_name, raw in fault_words_raw.items():
        decoded[word_name] = decode_fault_word(
            raw, FAULT_WORD_DEFINITIONS.get(word_name, {})
        )
    return decoded


def flatten_active_faults(fault_categories: Dict[str, List[str]]) -> List[str]:
    active_faults: List[str] = []
    for category, faults in fault_categories.items():
        pretty_category = category.replace("_", " ").title()
        for fault in faults:
            active_faults.append(f"{pretty_category}: {fault}")
    return active_faults


def read_telemetry(driver: PcsModbusTcpDriver) -> Dict[str, Any]:
    """
    Read foundation-level Njoy/Enjoy PCS telemetry.

    Read a few small blocks instead of one huge block.
    This is easier to debug with ModSim.
    """

    # Block 1: AC values from 0x6020 to 0x603C
    ac_start = REG_OUTPUT_AB_LINE_VOLTAGE
    ac_count = REG_AC_POWER_FACTOR - ac_start + 1
    ac_regs = driver.read_holding_registers(ac_start, ac_count)

    def ac(offset: int) -> int:
        return ac_regs[offset]

    # Block 2: DC/status values from 0x6050 to 0x605C
    dc_start = REG_BUS_VOLTAGE
    dc_count = REG_GRID_OFFGRID_STATUS - dc_start + 1
    dc_regs = driver.read_holding_registers(dc_start, dc_count)

    def dc(offset: int) -> int:
        return dc_regs[offset]

    operating_status_raw = dc(REG_OPERATING_STATUS - dc_start)
    grid_offgrid_status_raw = dc(REG_GRID_OFFGRID_STATUS - dc_start)

    telemetry = {
        "vendor": VENDOR_NAME,

        "ab_voltage_v": raw_to_s16(ac(REG_OUTPUT_AB_LINE_VOLTAGE - ac_start)) / 10.0,
        "bc_voltage_v": raw_to_s16(ac(REG_OUTPUT_BC_LINE_VOLTAGE - ac_start)) / 10.0,
        "ca_voltage_v": raw_to_s16(ac(REG_OUTPUT_CA_LINE_VOLTAGE - ac_start)) / 10.0,

        "phase_a_voltage_v": raw_to_s16(ac(REG_OUTPUT_PHASE_A_VOLTAGE - ac_start)) / 10.0,
        "phase_b_voltage_v": raw_to_s16(ac(REG_OUTPUT_PHASE_B_VOLTAGE - ac_start)) / 10.0,
        "phase_c_voltage_v": raw_to_s16(ac(REG_OUTPUT_PHASE_C_VOLTAGE - ac_start)) / 10.0,

        "phase_a_current_a": raw_to_s16(ac(REG_OUTPUT_PHASE_A_CURRENT - ac_start)) / 10.0,
        "phase_b_current_a": raw_to_s16(ac(REG_OUTPUT_PHASE_B_CURRENT - ac_start)) / 10.0,
        "phase_c_current_a": raw_to_s16(ac(REG_OUTPUT_PHASE_C_CURRENT - ac_start)) / 10.0,

        "frequency_hz": raw_to_s16(ac(REG_GRID_FREQUENCY - ac_start)) / 100.0,

        "active_power_kw": raw_to_s16(ac(REG_TOTAL_AC_ACTIVE_POWER - ac_start)) / 10.0,
        "reactive_power_kvar": raw_to_s16(ac(REG_TOTAL_AC_REACTIVE_POWER - ac_start)) / 10.0,
        "apparent_power_kva": raw_to_s16(ac(REG_TOTAL_AC_APPARENT_POWER - ac_start)) / 10.0,
        "power_factor": raw_to_s16(ac(REG_AC_POWER_FACTOR - ac_start)) / 100.0,

        "bus_voltage_v": raw_to_s16(dc(REG_BUS_VOLTAGE - dc_start)) / 10.0,
        "battery_voltage_v": raw_to_s16(dc(REG_BATTERY_VOLTAGE - dc_start)) / 10.0,
        "battery_current_a": raw_to_s16(dc(REG_BATTERY_CURRENT - dc_start)) / 10.0,
        "dc_power_kw": raw_to_s16(dc(REG_DC_POWER - dc_start)) / 10.0,
        "dc_total_current_a": raw_to_s16(dc(REG_DC_TOTAL_CURRENT - dc_start)) / 10.0,

        "operating_status_raw": operating_status_raw,
        "operating_status": decode_operating_status(operating_status_raw),

        "grid_offgrid_status_raw": grid_offgrid_status_raw,
        "grid_offgrid_status": decode_grid_offgrid_status(grid_offgrid_status_raw),

        "igbt_temperature_c": raw_to_s16(dc(REG_IGBT_TEMPERATURE - dc_start)) / 10.0,
        "ambient_temperature_c": raw_to_s16(dc(REG_AMBIENT_TEMPERATURE - dc_start)) / 10.0,
        "inductance_temperature_c": raw_to_s16(dc(REG_INDUCTANCE_TEMPERATURE - dc_start)) / 10.0,
    }

    # Detailed fault words from 0x1700 to 0x1707.
    # Keep this read non-fatal so telemetry remains available even if a PCS
    # firmware build rejects the detailed fault block.
    try:
        fault_regs = driver.read_holding_registers(REG_HARDWARE_FAULT_WORD_1, 8)
        fault_words_raw = {
            "hardware_fault_word_1": fault_regs[0],
            "hardware_fault_word_2": fault_regs[1],
            "grid_fault_word": fault_regs[2],
            "bus_fault_word": fault_regs[3],
            "ac_capacitor_fault_word": fault_regs[4],
            "system_fault_word": fault_regs[5],
            "switch_fault_word": fault_regs[6],
            "other_fault_word": fault_regs[7],
        }
        fault_categories = decode_fault_words(fault_words_raw)
        active_faults = flatten_active_faults(fault_categories)

        telemetry.update({
            "hardware_fault_word_1_raw": fault_words_raw["hardware_fault_word_1"],
            "hardware_fault_word_2_raw": fault_words_raw["hardware_fault_word_2"],
            "grid_fault_word_raw": fault_words_raw["grid_fault_word"],
            "bus_fault_word_raw": fault_words_raw["bus_fault_word"],
            "ac_capacitor_fault_word_raw": fault_words_raw["ac_capacitor_fault_word"],
            "system_fault_word_raw": fault_words_raw["system_fault_word"],
            "switch_fault_word_raw": fault_words_raw["switch_fault_word"],
            "other_fault_word_raw": fault_words_raw["other_fault_word"],
            "fault_words_raw": fault_words_raw,
            "fault_categories": fault_categories,
            "active_faults": active_faults,
            "fault_count": len(active_faults),
            "detailed_fault_status": len(active_faults) > 0,
            "fault_words_read_error": "",
        })
    except Exception as exc:
        telemetry.update({
            "hardware_fault_word_1_raw": None,
            "hardware_fault_word_2_raw": None,
            "grid_fault_word_raw": None,
            "bus_fault_word_raw": None,
            "ac_capacitor_fault_word_raw": None,
            "system_fault_word_raw": None,
            "switch_fault_word_raw": None,
            "other_fault_word_raw": None,
            "fault_words_raw": {},
            "fault_categories": {},
            "active_faults": [],
            "fault_count": 0,
            "detailed_fault_status": False,
            "fault_words_read_error": str(exc),
        })

    telemetry["fault_status"] = (
        telemetry.get("detailed_fault_status") is True
        or str(telemetry.get("operating_status", "")).lower() == "fault"
        or str(telemetry.get("grid_offgrid_status", "")).lower() == "fault"
    )

    return telemetry


def power_on(driver: PcsModbusTcpDriver):
    return driver.write_register(REG_POWER_ON_OFF_COMMAND, 1)


def power_off(driver: PcsModbusTcpDriver):
    return driver.write_register(REG_POWER_ON_OFF_COMMAND, 0)


def set_active_power_kw(driver: PcsModbusTcpDriver, power_kw: float):
    """
    EMS convention for now:
    +ve value = discharge/export
    -ve value = charge/import

    Njoy convention is same:
    +ve = discharge
    -ve = charge
    """
    raw = kw_to_raw(power_kw)
    return driver.write_register(REG_ACTIVE_POWER_SETTING, raw)


def set_reactive_power_kvar(driver: PcsModbusTcpDriver, reactive_power_kvar: float):
    raw = kvar_to_raw(reactive_power_kvar)
    return driver.write_register(REG_REACTIVE_POWER_SETTING, raw)


def reset_fault(driver: PcsModbusTcpDriver):
    return driver.write_register(REG_FAULT_RESET_COMMAND, 1)


def write_heartbeat(driver: PcsModbusTcpDriver, value: int):
    value = value % 256
    return driver.write_register(REG_HEARTBEAT, value)