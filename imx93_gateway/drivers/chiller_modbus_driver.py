"""
Chiller Modbus RTU Driver for i.MX93 EMS Gateway.

This driver is built from:
1. Liquid Cooling System Control Communication Protocol document
2. Already working test scripts:
   - chiller_read.py
   - chiller_control.py
   - chiller_read_mode.py
   - chiller_set_mode.py
   - chiller_set_temp_debug.py
   - scan_chiller_id.py

Protocol summary:
- Physical layer: RS485 / Modbus RTU
- Serial config: 9600 bps, 8 data bits, no parity, 1 stop bit
- Slave ID range: 1 to 128
- Minimum interval between instructions: >= 200 ms

Telemetry / status:
- Function code 0x04: Read Input Registers
- Registers 0 to 11

Control / setting:
- Function code 0x03: Read Holding Registers
- Function code 0x06: Write Single Holding Register
- Function code 0x10: Write Multiple Holding Registers
- Register 200: Control mode
- Register 201: System ON/OFF enable
- Register 205: Unit set temperature
"""

import argparse
import sys
import time
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


# -------------------------------------------------
# Import support
# -------------------------------------------------

CURRENT_FILE = Path(__file__).resolve()
IMX93_GATEWAY_DIR = CURRENT_FILE.parents[1]

if str(IMX93_GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(IMX93_GATEWAY_DIR))

try:
    from models.chiller_state import ChillerState
except ImportError:
    ChillerState = None


# -------------------------------------------------
# Pymodbus import compatibility
# -------------------------------------------------

try:
    from pymodbus.client import ModbusSerialClient
except ImportError:
    from pymodbus.client.sync import ModbusSerialClient


class ChillerModbusDriver:
    """
    Liquid cooling system / chiller Modbus RTU driver.

    This class hides all raw Modbus register-level details from the rest
    of the EMS gateway backend.
    """

    DEFAULT_PORT = "/dev/ttyUSB0"
    DEFAULT_BAUDRATE = 9600
    DEFAULT_BYTESIZE = 8
    DEFAULT_PARITY = "N"
    DEFAULT_STOPBITS = 1
    DEFAULT_TIMEOUT_SEC = 2.0
    DEFAULT_RETRIES = 1
    DEFAULT_SLAVE_ID = 1

    MIN_COMMAND_INTERVAL_SEC = 0.2

    # -------------------------------------------------
    # Input Registers: Function Code 0x04
    # -------------------------------------------------

    INPUT_REG_WATER_PUMP_STATUS = 0
    INPUT_REG_COMPRESSOR_1_STATUS = 1
    INPUT_REG_COMPRESSOR_2_STATUS = 2
    INPUT_REG_ELECTRIC_HEATER_STATUS = 3
    INPUT_REG_CONDENSATE_FAN_STATUS = 4
    INPUT_REG_OUTLET_WATER_TEMP = 5
    INPUT_REG_RETURN_WATER_TEMP = 6
    INPUT_REG_OUTLET_WATER_PRESSURE = 7
    INPUT_REG_RETURN_WATER_PRESSURE = 8
    INPUT_REG_EXTERNAL_AMBIENT_TEMP = 9
    INPUT_REG_MAKEUP_WATER_PUMP_STATUS = 10
    INPUT_REG_FAULT_ALARM_CODE = 11

    INPUT_REG_START = 0
    INPUT_REG_TELEMETRY_COUNT = 12

    INPUT_REG_RESERVED_START = 12
    INPUT_REG_RESERVED_END = 90
    INPUT_REG_ALL_COUNT_0_TO_90 = 91

    # -------------------------------------------------
    # Holding Registers: Function Code 0x03 / 0x06 / 0x10
    # -------------------------------------------------

    HOLDING_REG_CONTROL_MODE = 200
    HOLDING_REG_ON_OFF_ENABLE = 201
    HOLDING_REG_RESERVED_202 = 202
    HOLDING_REG_RESERVED_203 = 203
    HOLDING_REG_RESERVED_204 = 204
    HOLDING_REG_SET_TEMPERATURE = 205
    HOLDING_REG_RESERVED_206 = 206
    HOLDING_REG_RESERVED_207 = 207
    HOLDING_REG_RESERVED_208 = 208

    HOLDING_REG_SETTINGS_START = 200
    HOLDING_REG_SETTINGS_COUNT_200_TO_208 = 9

    CHILLER_OFF_VALUE = 0
    CHILLER_ON_VALUE = 1

    # Write values:
    #   0 = System automatic control mode
    #   1 = Refrigeration / Cooling mode
    #   2 = Heating mode
    #   3 = Water pump circulation mode
    WRITE_MODE_MAP = {
        0: "System automatic control mode",
        1: "Refrigeration / Cooling mode",
        2: "Heating mode",
        3: "Water pump circulation mode",
    }

    # Readback values:
    #   1 = Water pump circulation mode
    #   2 = Refrigeration / Cooling mode
    #   3 = Heating mode
    #   4 = System automatic control mode
    READ_MODE_MAP = {
        1: "Water pump circulation mode",
        2: "Refrigeration / Cooling mode",
        3: "Heating mode",
        4: "System automatic control mode",
    }

    MODE_NAME_TO_WRITE_VALUE = {
        "auto": 0,
        "automatic": 0,
        "system_auto": 0,
        "system_automatic": 0,
        "system automatic control mode": 0,

        "cool": 1,
        "cooling": 1,
        "refrigeration": 1,
        "refrigeration / cooling mode": 1,

        "heat": 2,
        "heating": 2,
        "heating mode": 2,

        "pump": 3,
        "water_pump": 3,
        "water_pump_circulation": 3,
        "water pump circulation mode": 3,
    }

    WRITE_VALUE_TO_EXPECTED_READBACK = {
        0: 4,
        1: 2,
        2: 3,
        3: 1,
    }

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        slave_id: int = DEFAULT_SLAVE_ID,
        baudrate: int = DEFAULT_BAUDRATE,
        bytesize: int = DEFAULT_BYTESIZE,
        parity: str = DEFAULT_PARITY,
        stopbits: int = DEFAULT_STOPBITS,
        timeout: float = DEFAULT_TIMEOUT_SEC,
        retries: int = DEFAULT_RETRIES,
        min_command_interval_sec: float = MIN_COMMAND_INTERVAL_SEC,
        signed_temperatures: bool = False,
    ):
        self.port = port
        self.slave_id = int(slave_id)
        self.baudrate = int(baudrate)
        self.bytesize = int(bytesize)
        self.parity = parity
        self.stopbits = int(stopbits)
        self.timeout = float(timeout)
        self.retries = int(retries)
        self.min_command_interval_sec = max(float(min_command_interval_sec), self.MIN_COMMAND_INTERVAL_SEC)
        self.signed_temperatures = signed_temperatures

        self.client: Optional[ModbusSerialClient] = None

        self._modbus_lock = threading.Lock()
        self._last_command_time = 0.0

    # -------------------------------------------------
    # Connection handling
    # -------------------------------------------------

    def connect(self) -> bool:
        """
        Open Modbus RTU serial connection.
        """

        kwargs = {
            "port": self.port,
            "baudrate": self.baudrate,
            "bytesize": self.bytesize,
            "parity": self.parity,
            "stopbits": self.stopbits,
            "timeout": self.timeout,
        }

        try:
            self.client = ModbusSerialClient(**kwargs, retries=self.retries)
        except TypeError:
            self.client = ModbusSerialClient(**kwargs)

        connected = self.client.connect()

        if connected:
            print(
                f"[MODBUS] Connected on {self.port} | "
                f"slave_id={self.slave_id}, baudrate={self.baudrate}, "
                f"{self.bytesize}{self.parity}{self.stopbits}"
            )

            # Your working scripts wait 0.2 sec after connect before first command.
            self._last_command_time = time.monotonic()
        else:
            print(f"[MODBUS] Failed to open {self.port}")

        return bool(connected)

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            print("[MODBUS] Connection closed")

    def is_connected(self) -> bool:
        return self.client is not None

    def _ensure_connected(self) -> None:
        if self.client is None:
            raise RuntimeError("Modbus client is not connected. Call connect() first.")

    # -------------------------------------------------
    # Modbus transaction helpers
    # -------------------------------------------------

    def _wait_command_gap(self) -> None:
        """
        Enforce >= 200 ms gap between Modbus instructions.
        """

        now = time.monotonic()
        elapsed = now - self._last_command_time

        if elapsed < self.min_command_interval_sec:
            time.sleep(self.min_command_interval_sec - elapsed)

    def _mark_command_time(self) -> None:
        self._last_command_time = time.monotonic()

    def _call_modbus_with_id_compat(self, func, **kwargs):
        """
        Supports pymodbus keyword differences.

        Your working scripts use:
            device_id=SLAVE_ID

        Other versions may use:
            slave=SLAVE_ID
            unit=SLAVE_ID
        """

        last_error = None

        for id_keyword in ("device_id", "slave", "unit"):
            call_kwargs = dict(kwargs)
            call_kwargs[id_keyword] = self.slave_id

            try:
                return func(**call_kwargs)
            except TypeError as exc:
                last_error = exc
                continue

        raise last_error

    @staticmethod
    def _validate_response(result: Any, operation_name: str) -> Any:
        if result is None:
            raise RuntimeError(f"{operation_name} failed: no response")

        if hasattr(result, "isError") and result.isError():
            raise RuntimeError(f"{operation_name} failed: {result}")

        return result

    def _transaction(self, operation_name: str, func, **kwargs) -> Any:
        """
        Thread-safe Modbus transaction with protocol delay.
        """

        self._ensure_connected()

        with self._modbus_lock:
            self._wait_command_gap()

            try:
                result = self._call_modbus_with_id_compat(func, **kwargs)
                return self._validate_response(result, operation_name)
            finally:
                self._mark_command_time()

    # -------------------------------------------------
    # Raw Modbus APIs
    # -------------------------------------------------

    def read_input_registers_raw(self, address: int, count: int) -> List[int]:
        """
        Read input registers using function code 0x04.
        Used for telemetry/status registers.
        """

        result = self._transaction(
            operation_name=f"read_input_registers(address={address}, count={count})",
            func=self.client.read_input_registers,
            address=int(address),
            count=int(count),
        )

        return list(result.registers)

    def read_holding_registers_raw(self, address: int, count: int) -> List[int]:
        """
        Read holding registers using function code 0x03.
        Used for control/setting registers.
        """

        result = self._transaction(
            operation_name=f"read_holding_registers(address={address}, count={count})",
            func=self.client.read_holding_registers,
            address=int(address),
            count=int(count),
        )

        return list(result.registers)

    def write_single_register(self, address: int, value: int) -> bool:
        """
        Write a single holding register using function code 0x06.
        """

        self._transaction(
            operation_name=f"write_register(address={address}, value={value})",
            func=self.client.write_register,
            address=int(address),
            value=int(value),
        )

        return True

    def write_multiple_registers(self, address: int, values: List[int]) -> bool:
        """
        Write multiple holding registers using function code 0x10.
        """

        self._transaction(
            operation_name=f"write_registers(address={address}, values={values})",
            func=self.client.write_registers,
            address=int(address),
            values=[int(v) for v in values],
        )

        return True

    # -------------------------------------------------
    # Decode helpers
    # -------------------------------------------------

    @staticmethod
    def _u16_to_s16(value: int) -> int:
        value = int(value) & 0xFFFF
        return value - 0x10000 if value & 0x8000 else value

    def _decode_temperature(self, raw_value: int) -> float:
        raw = self._u16_to_s16(raw_value) if self.signed_temperatures else int(raw_value)
        return raw / 10.0

    @staticmethod
    def _encode_temperature(temperature_celsius: Union[int, float, str]) -> int:
        return int(float(temperature_celsius) * 10)

    @staticmethod
    def _decode_pressure(raw_value: int) -> float:
        return int(raw_value) / 100.0

    @staticmethod
    def _running_status(raw_value: int) -> str:
        return "RUNNING" if int(raw_value) else "STOPPED"

    @staticmethod
    def _on_off_status(raw_value: int) -> str:
        return "ON" if int(raw_value) else "OFF"

    # -------------------------------------------------
    # Decode telemetry registers
    # -------------------------------------------------

    def decode_telemetry_registers_to_dict(self, regs: List[int]) -> Dict[str, Any]:
        """
        Decode input registers 0 to 11 into a clean dictionary.
        """

        if len(regs) < self.INPUT_REG_TELEMETRY_COUNT:
            raise ValueError(
                f"Expected {self.INPUT_REG_TELEMETRY_COUNT} telemetry registers, got {len(regs)}"
            )

        return {
            "water_pump": self._running_status(regs[0]),
            "compressor1": self._running_status(regs[1]),
            "compressor2": self._running_status(regs[2]),
            "electric_heater": self._running_status(regs[3]),
            "condensate_fan": self._running_status(regs[4]),
            "outlet_water_temp": self._decode_temperature(regs[5]),
            "return_water_temp": self._decode_temperature(regs[6]),
            "outlet_water_pressure": self._decode_pressure(regs[7]),
            "return_water_pressure": self._decode_pressure(regs[8]),
            "ambient_temp": self._decode_temperature(regs[9]),
            "makeup_pump": self._on_off_status(regs[10]),
            "fault_code": int(regs[11]),
            "raw_registers": list(regs),
            "communication_status": "online",
        }

    def decode_telemetry_registers(self, regs: List[int]) -> Any:
        """
        Decode input registers 0 to 11 into ChillerState if available,
        otherwise return dictionary.
        """

        data = self.decode_telemetry_registers_to_dict(regs)

        if ChillerState is None:
            return data

        state = ChillerState()

        state.water_pump = data["water_pump"]
        state.compressor1 = data["compressor1"]
        state.compressor2 = data["compressor2"]
        state.electric_heater = data["electric_heater"]
        state.condensate_fan = data["condensate_fan"]
        state.makeup_pump = data["makeup_pump"]

        state.outlet_water_temp = data["outlet_water_temp"]
        state.return_water_temp = data["return_water_temp"]
        state.outlet_water_pressure = data["outlet_water_pressure"]
        state.return_water_pressure = data["return_water_pressure"]
        state.ambient_temp = data["ambient_temp"]

        state.fault_code = data["fault_code"]
        state.communication_status = "online"
        state.update_timestamp()

        return state

    # -------------------------------------------------
    # Public telemetry/status read APIs
    # -------------------------------------------------

    def read_all_parameters(self) -> Any:
        """
        Read all live telemetry/status parameters.

        Equivalent to working chiller_read.py:
            read_input_registers(address=0, count=12, device_id=SLAVE_ID)
        """

        regs = self.read_input_registers_raw(
            address=self.INPUT_REG_START,
            count=self.INPUT_REG_TELEMETRY_COUNT,
        )

        print(f"[MODBUS] Raw telemetry registers 0-11: {regs}")

        return self.decode_telemetry_registers(regs)

    def read_all_parameters_dict(self) -> Dict[str, Any]:
        regs = self.read_input_registers_raw(
            address=self.INPUT_REG_START,
            count=self.INPUT_REG_TELEMETRY_COUNT,
        )

        return self.decode_telemetry_registers_to_dict(regs)

    def read_all_input_registers_0_to_90(self) -> List[int]:
        """
        Read input registers 0 to 90, including reserved registers.
        Use only for debugging/exploration.
        """

        regs = self.read_input_registers_raw(
            address=self.INPUT_REG_START,
            count=self.INPUT_REG_ALL_COUNT_0_TO_90,
        )

        print(f"[MODBUS] Raw input registers 0-90: {regs}")
        return regs

    def read_fault_alarm_code(self) -> int:
        regs = self.read_input_registers_raw(
            address=self.INPUT_REG_FAULT_ALARM_CODE,
            count=1,
        )

        fault_code = int(regs[0])
        print(f"[MODBUS] Fault alarm code: {fault_code}")
        return fault_code

    # -------------------------------------------------
    # Public setting/control read APIs
    # -------------------------------------------------

    def read_control_mode(self) -> Dict[str, Any]:
        """
        Read control mode from holding register 200.
        """

        regs = self.read_holding_registers_raw(
            address=self.HOLDING_REG_CONTROL_MODE,
            count=1,
        )

        raw_value = int(regs[0])

        result = {
            "register": self.HOLDING_REG_CONTROL_MODE,
            "raw_value": raw_value,
            "mode": self.READ_MODE_MAP.get(raw_value, "Unknown mode"),
        }

        print(f"[MODBUS] Current control mode: {result}")
        return result

    def read_on_off_enable(self) -> Dict[str, Any]:
        """
        Read ON/OFF enable from holding register 201.
        """

        regs = self.read_holding_registers_raw(
            address=self.HOLDING_REG_ON_OFF_ENABLE,
            count=1,
        )

        raw_value = int(regs[0])

        result = {
            "register": self.HOLDING_REG_ON_OFF_ENABLE,
            "raw_value": raw_value,
            "status": self._on_off_status(raw_value),
        }

        print(f"[MODBUS] ON/OFF enable: {result}")
        return result

    def read_set_temperature(self) -> Dict[str, Any]:
        """
        Read set temperature from holding register 205.
        """

        regs = self.read_holding_registers_raw(
            address=self.HOLDING_REG_SET_TEMPERATURE,
            count=1,
        )

        raw_value = int(regs[0])

        result = {
            "register": self.HOLDING_REG_SET_TEMPERATURE,
            "raw_value": raw_value,
            "temperature_celsius": raw_value / 10.0,
        }

        print(f"[MODBUS] Set temperature: {result}")
        return result

    def read_setting_parameters(self) -> Dict[str, Any]:
        """
        Read holding registers 200 to 208.

        Includes:
            200: Control mode
            201: ON/OFF enable
            202-204: Reserved
            205: Set temperature
            206-208: Reserved
        """

        regs = self.read_holding_registers_raw(
            address=self.HOLDING_REG_SETTINGS_START,
            count=self.HOLDING_REG_SETTINGS_COUNT_200_TO_208,
        )

        control_mode_raw = int(regs[0])
        on_off_raw = int(regs[1])
        set_temp_raw = int(regs[5])

        result = {
            "raw_registers_200_to_208": list(regs),
            "control_mode": {
                "register": 200,
                "raw_value": control_mode_raw,
                "mode": self.READ_MODE_MAP.get(control_mode_raw, "Unknown mode"),
            },
            "on_off_enable": {
                "register": 201,
                "raw_value": on_off_raw,
                "status": self._on_off_status(on_off_raw),
            },
            "reserved_202": int(regs[2]),
            "reserved_203": int(regs[3]),
            "reserved_204": int(regs[4]),
            "set_temperature": {
                "register": 205,
                "raw_value": set_temp_raw,
                "temperature_celsius": set_temp_raw / 10.0,
            },
            "reserved_206": int(regs[6]),
            "reserved_207": int(regs[7]),
            "reserved_208": int(regs[8]),
        }

        print(f"[MODBUS] Setting parameters 200-208: {result}")
        return result

    # -------------------------------------------------
    # Public write/control APIs
    # -------------------------------------------------

    def turn_on(self, verify: bool = False) -> Dict[str, Any]:
        """
        Turn ON liquid cooling system.
        Writes register 201 = 1.
        """

        self.write_single_register(
            address=self.HOLDING_REG_ON_OFF_ENABLE,
            value=self.CHILLER_ON_VALUE,
        )

        result = {
            "status": "ok",
            "command": "CHILLER_ON",
            "register": self.HOLDING_REG_ON_OFF_ENABLE,
            "written_value": self.CHILLER_ON_VALUE,
            "message": "Chiller ON command sent successfully",
        }

        if verify:
            time.sleep(0.5)
            result["readback"] = self.read_on_off_enable()

        print(f"[MODBUS] {result['message']}")
        return result

    def turn_off(self, verify: bool = False) -> Dict[str, Any]:
        """
        Turn OFF liquid cooling system.
        Writes register 201 = 0.
        """

        self.write_single_register(
            address=self.HOLDING_REG_ON_OFF_ENABLE,
            value=self.CHILLER_OFF_VALUE,
        )

        result = {
            "status": "ok",
            "command": "CHILLER_OFF",
            "register": self.HOLDING_REG_ON_OFF_ENABLE,
            "written_value": self.CHILLER_OFF_VALUE,
            "message": "Chiller OFF command sent successfully",
        }

        if verify:
            time.sleep(0.5)
            result["readback"] = self.read_on_off_enable()

        print(f"[MODBUS] {result['message']}")
        return result

    def normalize_control_mode(self, mode: Union[int, str]) -> int:
        if isinstance(mode, int):
            if mode in self.WRITE_MODE_MAP:
                return mode
            raise ValueError("Invalid mode. Allowed integer values: 0, 1, 2, 3")

        mode_str = str(mode).strip().lower()

        if mode_str.isdigit():
            mode_int = int(mode_str)
            if mode_int in self.WRITE_MODE_MAP:
                return mode_int

        if mode_str in self.MODE_NAME_TO_WRITE_VALUE:
            return self.MODE_NAME_TO_WRITE_VALUE[mode_str]

        raise ValueError(
            "Invalid mode. Allowed: 0/auto, 1/cooling, 2/heating, 3/pump"
        )

    def set_control_mode(self, mode: Union[int, str], verify: bool = True) -> Dict[str, Any]:
        """
        Set chiller control mode.
        Writes register 200 = 0/1/2/3.
        """

        write_value = self.normalize_control_mode(mode)
        requested_mode = self.WRITE_MODE_MAP[write_value]

        self.write_single_register(
            address=self.HOLDING_REG_CONTROL_MODE,
            value=write_value,
        )

        result = {
            "status": "ok",
            "command": "SET_MODE",
            "register": self.HOLDING_REG_CONTROL_MODE,
            "written_value": write_value,
            "requested_mode": requested_mode,
            "message": "Mode write command sent successfully",
        }

        if verify:
            time.sleep(0.5)
            readback = self.read_control_mode()
            expected_readback_value = self.WRITE_VALUE_TO_EXPECTED_READBACK[write_value]

            result["readback"] = readback
            result["expected_readback_value"] = expected_readback_value
            result["verified"] = readback["raw_value"] == expected_readback_value

        print(f"[MODBUS] {result}")
        return result

    def set_temperature(self, temperature_celsius: Union[int, float, str], verify: bool = True) -> Dict[str, Any]:
        """
        Set chiller temperature.
        Writes register 205 = temperature * 10.
        """

        temp_c = float(temperature_celsius)
        raw_value = self._encode_temperature(temp_c)

        self.write_single_register(
            address=self.HOLDING_REG_SET_TEMPERATURE,
            value=raw_value,
        )

        result = {
            "status": "ok",
            "command": "SET_TEMP",
            "register": self.HOLDING_REG_SET_TEMPERATURE,
            "temperature_celsius": temp_c,
            "written_value": raw_value,
            "message": "Temperature write command sent successfully",
        }

        if verify:
            time.sleep(1.0)
            readback = self.read_set_temperature()

            result["readback"] = readback
            result["verified"] = readback["raw_value"] == raw_value

        print(f"[MODBUS] {result}")
        return result

    def apply_basic_control(
        self,
        on_off: Optional[Union[bool, int, str]] = None,
        mode: Optional[Union[int, str]] = None,
        temperature_celsius: Optional[Union[int, float, str]] = None,
        verify: bool = True,
    ) -> Dict[str, Any]:
        """
        Apply multiple controls sequentially.
        Each individual command still respects the >=200 ms interval.
        """

        result: Dict[str, Any] = {}

        if on_off is not None:
            on_off_str = str(on_off).strip().lower()

            if on_off is True or on_off_str in ("1", "on", "true", "start"):
                result["on_off"] = self.turn_on(verify=verify)
            elif on_off is False or on_off_str in ("0", "off", "false", "stop"):
                result["on_off"] = self.turn_off(verify=verify)
            else:
                raise ValueError("on_off must be ON/OFF, 1/0, True/False, START/STOP")

        if mode is not None:
            result["mode"] = self.set_control_mode(mode, verify=verify)

        if temperature_celsius is not None:
            result["temperature"] = self.set_temperature(temperature_celsius, verify=verify)

        return result

    # -------------------------------------------------
    # Scanner
    # -------------------------------------------------

    def scan_slave_ids(self, start_id: int = 1, end_id: int = 128, stop_on_first: bool = True) -> List[int]:
        """
        Scan chiller slave IDs from 1 to 128.
        """

        start_id = max(1, int(start_id))
        end_id = min(128, int(end_id))

        original_slave_id = self.slave_id
        found_ids: List[int] = []

        print(f"[MODBUS] Scanning chiller slave IDs {start_id} to {end_id}...")

        try:
            for sid in range(start_id, end_id + 1):
                self.slave_id = sid

                try:
                    regs = self.read_input_registers_raw(address=0, count=1)
                    print(f"[MODBUS] Found chiller slave ID: {sid}, register 0 value: {regs[0]}")
                    found_ids.append(sid)

                    if stop_on_first:
                        break

                except Exception:
                    pass

        finally:
            self.slave_id = original_slave_id

        if not found_ids:
            print("[MODBUS] No chiller found")

        return found_ids


# -------------------------------------------------
# CLI test support
# -------------------------------------------------

def _state_to_dict(state: Any) -> Dict[str, Any]:
    if hasattr(state, "to_dict"):
        return state.to_dict()
    if isinstance(state, dict):
        return state
    return vars(state)


def _print_dict(title: str, data: Dict[str, Any]) -> None:
    print(f"\n---------------- {title} ----------------")
    for key, value in data.items():
        print(f"{key:30}: {value}")
    print("-" * (len(title) + 34))


def main() -> None:
    parser = argparse.ArgumentParser(description="Chiller Modbus RTU Driver Test CLI")
    parser.add_argument(
        "command",
        choices=[
            "read",
            "settings",
            "read_mode",
            "read_temp",
            "read_onoff",
            "on",
            "off",
            "set_mode",
            "set_temp",
            "scan",
        ],
        help="Command to execute",
    )
    parser.add_argument("value", nargs="?", help="Value for set_mode or set_temp")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port")
    parser.add_argument("--slave-id", type=int, default=1, help="Modbus slave ID")
    parser.add_argument("--no-verify", action="store_true", help="Disable write readback verification")

    args = parser.parse_args()

    driver = ChillerModbusDriver(
        port=args.port,
        slave_id=args.slave_id,
    )

    if not driver.connect():
        sys.exit(1)

    try:
        if args.command == "read":
            state = driver.read_all_parameters()
            _print_dict("CHILLER TELEMETRY", _state_to_dict(state))

        elif args.command == "settings":
            settings = driver.read_setting_parameters()
            _print_dict("CHILLER SETTINGS", settings)

        elif args.command == "read_mode":
            mode = driver.read_control_mode()
            _print_dict("CHILLER MODE", mode)

        elif args.command == "read_temp":
            temp = driver.read_set_temperature()
            _print_dict("CHILLER SET TEMPERATURE", temp)

        elif args.command == "read_onoff":
            status = driver.read_on_off_enable()
            _print_dict("CHILLER ON/OFF", status)

        elif args.command == "on":
            result = driver.turn_on(verify=not args.no_verify)
            _print_dict("CHILLER ON RESULT", result)

        elif args.command == "off":
            result = driver.turn_off(verify=not args.no_verify)
            _print_dict("CHILLER OFF RESULT", result)

        elif args.command == "set_mode":
            if args.value is None:
                raise ValueError("set_mode requires value: 0/1/2/3 or auto/cooling/heating/pump")
            result = driver.set_control_mode(args.value, verify=not args.no_verify)
            _print_dict("SET MODE RESULT", result)

        elif args.command == "set_temp":
            if args.value is None:
                raise ValueError("set_temp requires temperature value, e.g. 25.0")
            result = driver.set_temperature(args.value, verify=not args.no_verify)
            _print_dict("SET TEMP RESULT", result)

        elif args.command == "scan":
            found = driver.scan_slave_ids()
            _print_dict("SCAN RESULT", {"found_ids": found})

    except Exception as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    finally:
        driver.close()


if __name__ == "__main__":
    main()