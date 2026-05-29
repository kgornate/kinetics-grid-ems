#!/usr/bin/env python3
"""
Inpower / Empower 125kW PCS Modbus TCP Profile

Purpose:
- Vendor-specific register map and scaling for Inpower/Empower 125kW PCS.
- Used by the common PCS Gateway Service.
- Converts vendor-specific Modbus data into common EMS-level PCS telemetry.

Important protocol points:
- Ethernet Modbus TCP.
- Default PCS IP in vendor document: 192.168.0.20
- Default port: 502
- Default Modbus station/unit ID: 1
- Remote control commands use coils.
- Telemetry uses input registers.
- PCS setpoints/settings use holding registers.

EMS convention used by our gateway:
- +ve active power = discharge/export
- -ve active power = charge/import

Inpower active power command convention:
- Negative setpoint means discharging to grid
- Positive setpoint means charging from grid

Therefore:
- EMS +20 kW discharge  -> Inpower raw -200
- EMS -20 kW charge     -> Inpower raw +200
"""

from typing import Any, Dict, Optional

from drivers.pcs_modbus_tcp_driver import PcsModbusTcpDriver


VENDOR_NAME = "inpower_125kw"

DEFAULT_HOST = "192.168.0.20"
DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 1


# -------------------------------------------------
# 0x Coil / Remote Control Addresses
# -------------------------------------------------

COIL_FAULT_RESET = 1
COIL_DEVICE_STARTUP = 2
COIL_DEVICE_SHUTDOWN = 3
COIL_REMOTE_EMERGENCY_STOP = 4
COIL_ACC_CHARGE_ENERGY_RESET = 5
COIL_ACC_DISCHARGE_ENERGY_RESET = 6
COIL_REMOTE_LOCAL_SETTING = 7
COIL_DEVICE_STANDBY = 8
COIL_STS_REMOTE_CONTROL = 12


# -------------------------------------------------
# 1x Discrete Input / Remote Signaling Addresses
# -------------------------------------------------

DI_SHUTDOWN_STATUS = 81
DI_STANDBY_STATUS = 82
DI_RUNNING_STATUS = 83
DI_TOTAL_FAULT_STATUS = 84
DI_TOTAL_ALARM_STATUS = 85
DI_REMOTE_LOCAL_STATUS = 86
DI_EMERGENCY_STOP_INPUT_STATUS = 87
DI_GRID_CONNECTED_STATUS = 88
DI_VF_OFFGRID_STATUS = 89
DI_OVERLOAD_DERATING = 90
DI_BMS_DRY_CONTACT_INPUT_STATUS = 94
DI_POSITIVE_DC_MAIN_BREAKER_STATUS = 95
DI_NEGATIVE_DC_MAIN_BREAKER_STATUS = 96
DI_STS_SWITCH_STATUS = 97


# -------------------------------------------------
# 3x Input Register / Telemetry Addresses
# -------------------------------------------------

REG_PHASE_A_VOLTAGE = 201
REG_PHASE_B_VOLTAGE = 202
REG_PHASE_C_VOLTAGE = 203

REG_PHASE_A_CURRENT = 204
REG_PHASE_B_CURRENT = 205
REG_PHASE_C_CURRENT = 206

REG_GRID_FREQUENCY = 207

REG_PHASE_A_ACTIVE_POWER = 208
REG_PHASE_B_ACTIVE_POWER = 209
REG_PHASE_C_ACTIVE_POWER = 210
REG_TOTAL_ACTIVE_POWER = 211

REG_PHASE_A_REACTIVE_POWER = 212
REG_PHASE_B_REACTIVE_POWER = 213
REG_PHASE_C_REACTIVE_POWER = 214
REG_TOTAL_REACTIVE_POWER = 215

REG_PHASE_A_APPARENT_POWER = 216
REG_PHASE_B_APPARENT_POWER = 217
REG_PHASE_C_APPARENT_POWER = 218
REG_TOTAL_APPARENT_POWER = 219

REG_PHASE_A_POWER_FACTOR = 220
REG_PHASE_B_POWER_FACTOR = 221
REG_PHASE_C_POWER_FACTOR = 222
REG_TOTAL_POWER_FACTOR = 223

REG_PCS_INPUT_POWER = 224
REG_PCS_INPUT_VOLTAGE = 225
REG_PCS_INPUT_CURRENT = 226

REG_PCS_RADIATOR_TEMP = 227
REG_BMS_OPERATING_STATUS = 228
REG_PCS_CURRENT_STATUS = 229

REG_PCS_COMMUNICATION_STATUS_WORD = 238


# -------------------------------------------------
# 4x Holding Register / Remote Regulation Addresses
# -------------------------------------------------

REG_RUNNING_MODE = 301
REG_CONSTANT_VOLTAGE_SETTING = 302
REG_CONSTANT_CURRENT_SETTING = 303
REG_ACTIVE_POWER_SETTING = 304
REG_REACTIVE_POWER_SETTING = 305
REG_GRID_OFFGRID_SETTING = 306

REG_OFFGRID_OUTPUT_VOLTAGE = 307
REG_OFFGRID_OUTPUT_FREQUENCY = 308

REG_ACTIVE_POWER_CONTROL_MODE = 325

REG_REACTIVE_POWER_MODE = 336
REG_POWER_FACTOR_SETTING = 337

REG_INSULATION_DETECTION_ENABLE = 341
REG_LEAKAGE_CURRENT_THRESHOLD = 342
REG_INSULATION_RESISTANCE_THRESHOLD = 343
REG_PRIMARY_FREQUENCY_REGULATION_ENABLE = 344


# Inpower startup/shutdown commands are coil commands.
# Coils may be momentary in a real PCS, so readback verification is not always reliable.
POWER_COMMAND_VERIFY_SUPPORTED = False

# Inpower document does not define a normal EMS heartbeat holding register like Njoy.
HEARTBEAT_SUPPORTED = False


# -------------------------------------------------
# Basic conversion helpers
# -------------------------------------------------

def raw_to_s16(raw: int) -> int:
    return PcsModbusTcpDriver.to_s16(raw)


def raw_to_u16(raw: int) -> int:
    return int(raw) & 0xFFFF


def ems_kw_to_inpower_raw(power_kw: float) -> int:
    """
    EMS convention:
    +ve kW = discharge/export
    -ve kW = charge/import

    Inpower command convention:
    -ve raw = discharging to grid
    +ve raw = charging from grid

    Scaling:
    kW x 10
    """
    return int(round(-power_kw * 10))


def inpower_raw_to_ems_kw(raw: int) -> float:
    """
    Convert Inpower active power setpoint raw value to EMS convention.
    """
    return -raw_to_s16(raw) / 10.0


def kw_to_raw(power_kw: float) -> int:
    """
    Common function name expected by PCS gateway service.

    For Inpower, this intentionally inverts sign.
    """
    return ems_kw_to_inpower_raw(power_kw)


def kvar_to_raw(reactive_power_kvar: float) -> int:
    """
    Reactive power setting scaling:
    kvar x 10

    Positive = inductive
    Negative = capacitive
    """
    return int(round(reactive_power_kvar * 10))


def decode_pcs_current_status(raw: int) -> str:
    """
    Decode Inpower PCS Current Status.

    Common values:
    0  - Shutdown
    1  - Self-check
    2  - Operation
    4  - Fault
    7  - Standby

    Newer revision also defines:
    10 - Charging
    11 - Discharging
    """
    mapping = {
        0: "shutdown",
        1: "self_check",
        2: "operation",
        4: "fault",
        7: "standby",
        10: "charging",
        11: "discharging",
    }
    return mapping.get(int(raw), f"unknown_{raw}")


def decode_grid_offgrid_status_from_discrete(discrete_status: Dict[str, Any]) -> str:
    if discrete_status.get("grid_connected_status") is True:
        return "grid_connected_operation"

    if discrete_status.get("vf_offgrid_status") is True:
        return "off_grid_operation"

    if discrete_status.get("shutdown_status") is True:
        return "shutdown"

    if discrete_status.get("standby_status") is True:
        return "standby"

    if discrete_status.get("fault_status") is True:
        return "fault"

    return "unknown"


def _bool_at(bits, address: int, start_address: int) -> Optional[bool]:
    idx = address - start_address
    if idx < 0 or idx >= len(bits):
        return None
    return bool(bits[idx])


# -------------------------------------------------
# Optional discrete status read
# -------------------------------------------------

def read_discrete_status(driver: PcsModbusTcpDriver) -> Dict[str, Any]:
    """
    Read Inpower discrete input statuses from 81 to 97.

    If the simulator does not support discrete inputs, the caller can ignore failure.
    """
    start = DI_SHUTDOWN_STATUS
    count = DI_STS_SWITCH_STATUS - start + 1

    bits = driver.read_discrete_inputs(start, count)

    return {
        "shutdown_status": _bool_at(bits, DI_SHUTDOWN_STATUS, start),
        "standby_status": _bool_at(bits, DI_STANDBY_STATUS, start),
        "running_status": _bool_at(bits, DI_RUNNING_STATUS, start),
        "fault_status": _bool_at(bits, DI_TOTAL_FAULT_STATUS, start),
        "alarm_status": _bool_at(bits, DI_TOTAL_ALARM_STATUS, start),
        "remote_local_status": _bool_at(bits, DI_REMOTE_LOCAL_STATUS, start),
        "emergency_stop_input_status": _bool_at(bits, DI_EMERGENCY_STOP_INPUT_STATUS, start),
        "grid_connected_status": _bool_at(bits, DI_GRID_CONNECTED_STATUS, start),
        "vf_offgrid_status": _bool_at(bits, DI_VF_OFFGRID_STATUS, start),
        "overload_derating": _bool_at(bits, DI_OVERLOAD_DERATING, start),
        "bms_dry_contact_input_status": _bool_at(bits, DI_BMS_DRY_CONTACT_INPUT_STATUS, start),
        "positive_dc_main_breaker_status": _bool_at(bits, DI_POSITIVE_DC_MAIN_BREAKER_STATUS, start),
        "negative_dc_main_breaker_status": _bool_at(bits, DI_NEGATIVE_DC_MAIN_BREAKER_STATUS, start),
        "sts_switch_status": _bool_at(bits, DI_STS_SWITCH_STATUS, start),
    }


# -------------------------------------------------
# Telemetry read
# -------------------------------------------------

def read_telemetry(driver: PcsModbusTcpDriver) -> Dict[str, Any]:
    """
    Read foundation-level Inpower PCS telemetry.

    We read input registers 201 to 229 using function code 0x04.
    This keeps the first integration simple and simulator-friendly.
    """

    start = REG_PHASE_A_VOLTAGE
    end = REG_PCS_CURRENT_STATUS
    count = end - start + 1

    regs = driver.read_input_registers(start, count)

    def r(address: int) -> int:
        return int(regs[address - start])

    pcs_status_raw = r(REG_PCS_CURRENT_STATUS)
    operating_status = decode_pcs_current_status(pcs_status_raw)

    discrete_status: Dict[str, Any] = {}
    grid_offgrid_status = "unknown"

    try:
        discrete_status = read_discrete_status(driver)
        grid_offgrid_status = decode_grid_offgrid_status_from_discrete(discrete_status)
    except Exception:
        # Discrete input block may not be configured in ModSim during basic testing.
        discrete_status = {}
        if operating_status in ("shutdown", "standby", "fault"):
            grid_offgrid_status = operating_status

    fault_status = (
        operating_status == "fault"
        or discrete_status.get("fault_status") is True
    )

    telemetry = {
        "vendor": VENDOR_NAME,

        # AC voltage/current
        "phase_a_voltage_v": raw_to_u16(r(REG_PHASE_A_VOLTAGE)) / 10.0,
        "phase_b_voltage_v": raw_to_u16(r(REG_PHASE_B_VOLTAGE)) / 10.0,
        "phase_c_voltage_v": raw_to_u16(r(REG_PHASE_C_VOLTAGE)) / 10.0,

        # Line voltage is not directly available in the basic Inpower block.
        # Keeping these as None so Flutter/common model remains stable.
        "ab_voltage_v": None,
        "bc_voltage_v": None,
        "ca_voltage_v": None,

        "phase_a_current_a": raw_to_s16(r(REG_PHASE_A_CURRENT)) / 10.0,
        "phase_b_current_a": raw_to_s16(r(REG_PHASE_B_CURRENT)) / 10.0,
        "phase_c_current_a": raw_to_s16(r(REG_PHASE_C_CURRENT)) / 10.0,

        "frequency_hz": raw_to_u16(r(REG_GRID_FREQUENCY)) / 100.0,

        # Power values
        # Note: telemetry sign convention is kept as reported by the PCS.
        "phase_a_active_power_kw": raw_to_s16(r(REG_PHASE_A_ACTIVE_POWER)) / 10.0,
        "phase_b_active_power_kw": raw_to_s16(r(REG_PHASE_B_ACTIVE_POWER)) / 10.0,
        "phase_c_active_power_kw": raw_to_s16(r(REG_PHASE_C_ACTIVE_POWER)) / 10.0,
        "active_power_kw": raw_to_s16(r(REG_TOTAL_ACTIVE_POWER)) / 10.0,

        "phase_a_reactive_power_kvar": raw_to_s16(r(REG_PHASE_A_REACTIVE_POWER)) / 10.0,
        "phase_b_reactive_power_kvar": raw_to_s16(r(REG_PHASE_B_REACTIVE_POWER)) / 10.0,
        "phase_c_reactive_power_kvar": raw_to_s16(r(REG_PHASE_C_REACTIVE_POWER)) / 10.0,
        "reactive_power_kvar": raw_to_s16(r(REG_TOTAL_REACTIVE_POWER)) / 10.0,

        "apparent_power_kva": raw_to_u16(r(REG_TOTAL_APPARENT_POWER)) / 10.0,
        "power_factor": raw_to_s16(r(REG_TOTAL_POWER_FACTOR)) / 1000.0,

        # DC/input side
        "dc_power_kw": raw_to_s16(r(REG_PCS_INPUT_POWER)) / 10.0,
        "bus_voltage_v": raw_to_s16(r(REG_PCS_INPUT_VOLTAGE)) / 10.0,
        "battery_voltage_v": raw_to_s16(r(REG_PCS_INPUT_VOLTAGE)) / 10.0,
        "battery_current_a": raw_to_s16(r(REG_PCS_INPUT_CURRENT)) / 10.0,
        "dc_total_current_a": raw_to_s16(r(REG_PCS_INPUT_CURRENT)) / 10.0,

        # Status
        "operating_status_raw": pcs_status_raw,
        "operating_status": operating_status,
        "grid_offgrid_status_raw": None,
        "grid_offgrid_status": grid_offgrid_status,
        "fault_status": fault_status,

        # Temperature
        "igbt_temperature_c": raw_to_s16(r(REG_PCS_RADIATOR_TEMP)),
        "ambient_temperature_c": None,
        "inductance_temperature_c": None,

        # Inpower-specific debug fields
        "bms_operating_status": raw_to_u16(r(REG_BMS_OPERATING_STATUS)),
        "discrete_status": discrete_status,
    }

    return telemetry


# -------------------------------------------------
# Control commands
# -------------------------------------------------

def power_on(driver: PcsModbusTcpDriver):
    """
    Start PCS.

    Inpower uses coil 00002 for device startup.
    """
    return driver.write_coil(COIL_DEVICE_STARTUP, True)


def power_off(driver: PcsModbusTcpDriver):
    """
    Shutdown PCS.

    Inpower uses coil 00003 for device shutdown.
    """
    return driver.write_coil(COIL_DEVICE_SHUTDOWN, True)


def standby(driver: PcsModbusTcpDriver):
    """
    Put PCS in standby.

    Inpower uses coil 00008 for standby.
    """
    return driver.write_coil(COIL_DEVICE_STANDBY, True)


def set_remote_mode(driver: PcsModbusTcpDriver, enabled: bool = True):
    """
    Set remote/local mode.

    Coil 00007:
    1 = Remote
    0 = Local
    """
    return driver.write_coil(COIL_REMOTE_LOCAL_SETTING, bool(enabled))


def reset_fault(driver: PcsModbusTcpDriver):
    """
    Fault reset.

    Inpower uses coil 00001 for fault reset.
    """
    return driver.write_coil(COIL_FAULT_RESET, True)


def set_active_power_kw(driver: PcsModbusTcpDriver, power_kw: float):
    """
    Set active power.

    EMS convention:
    +ve = discharge/export
    -ve = charge/import

    Inpower convention:
    -ve raw = discharge to grid
    +ve raw = charge from grid
    """
    raw = kw_to_raw(power_kw)
    return driver.write_register(REG_ACTIVE_POWER_SETTING, raw)


def set_reactive_power_kvar(driver: PcsModbusTcpDriver, reactive_power_kvar: float):
    raw = kvar_to_raw(reactive_power_kvar)
    return driver.write_register(REG_REACTIVE_POWER_SETTING, raw)


def set_running_mode(driver: PcsModbusTcpDriver, mode: int):
    """
    Running mode selection at 00301.

    Common values from protocol:
    0 - None
    1 - Constant current charging
    2 - Constant voltage charging
    3 - Constant power charging
    4 - DC voltage mode
    """
    return driver.write_register(REG_RUNNING_MODE, int(mode))


def set_grid_offgrid_mode(driver: PcsModbusTcpDriver, mode: int):
    """
    Grid-connected / off-grid setting at 00306.

    0 - On-grid mode
    1 - VF off-grid mode
    2 - VSG mode
    """
    return driver.write_register(REG_GRID_OFFGRID_SETTING, int(mode))


def set_total_power_control_mode(driver: PcsModbusTcpDriver):
    """
    00325 Active Power Control Mode:
    0 - Split-phase control
    1 - Total power control
    """
    return driver.write_register(REG_ACTIVE_POWER_CONTROL_MODE, 1)


def write_heartbeat(driver: PcsModbusTcpDriver, value: int):
    """
    Inpower does not define the same heartbeat register used in the Njoy profile.

    Kept here only so the common service can call it safely.
    """
    raise NotImplementedError("Inpower profile does not define a normal heartbeat register")