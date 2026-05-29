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

from typing import Dict, Any

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


def read_telemetry(driver: PcsModbusTcpDriver) -> Dict[str, Any]:
    """
    Read foundation-level Njoy/Enjoy PCS telemetry.

    For the first phase, we read a few small blocks instead of one huge block.
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