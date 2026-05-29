#!/usr/bin/env python3
"""
PCS Modbus TCP Driver

Purpose:
- Generic low-level Modbus TCP client for PCS/Inverter assets.
- This file does not know vendor-specific register maps.
- Vendor-specific logic should stay inside pcs_profiles/*.py files.

Supports:
- Read holding registers
- Read input registers
- Read coils
- Read discrete inputs
- Write single register
- Write multiple registers
- Write single coil

Compatible with pymodbus 2.x and 3.x style APIs.
"""

import time
from typing import List, Optional

try:
    # pymodbus 3.x
    from pymodbus.client import ModbusTcpClient
except ImportError:
    # pymodbus 2.x fallback
    from pymodbus.client.sync import ModbusTcpClient


class PcsModbusTcpDriver:
    def __init__(
        self,
        host: str,
        port: int = 502,
        unit_id: int = 1,
        timeout: float = 3.0,
        retries: int = 2,
        retry_delay: float = 0.5,
    ):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay
        self.client: Optional[ModbusTcpClient] = None

    def connect(self) -> bool:
        """
        Connect to Modbus TCP server with retry support.

        This helps with ModSim and real PCS devices where TCP connection
        may sometimes timeout if the previous session was closed recently.
        """
        last_error = None

        for attempt in range(self.retries + 1):
            try:
                if self.client:
                    try:
                        self.client.close()
                    except Exception:
                        pass
                    self.client = None

                self.client = ModbusTcpClient(
                    host=self.host,
                    port=self.port,
                    timeout=self.timeout,
                )

                if self.client.connect():
                    if attempt > 0:
                        print(f"[OK] TCP connected after retry attempt {attempt}")
                    return True

            except Exception as exc:
                last_error = exc

            if attempt < self.retries:
                print(
                    f"[WARN] TCP connect failed, retrying "
                    f"{attempt + 1}/{self.retries}..."
                )
                time.sleep(self.retry_delay)

        if last_error:
            print(f"[ERROR] TCP connect failed after retries: {last_error}")

        return False

    def close(self) -> None:
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            finally:
                self.client = None

    def _ensure_connected(self) -> None:
        if self.client is None:
            raise RuntimeError("Modbus TCP client is not initialized. Call connect() first.")

    def _reconnect(self) -> bool:
        """
        Close existing TCP socket and reconnect.
        Used when a read/write transaction fails.
        """
        self.close()
        return self.connect()

    def _call_with_unit_id(self, func, **kwargs):
        """
        Compatibility wrapper for different pymodbus versions.

        pymodbus 3.x may use:
            device_id

        pymodbus 2.x usually uses:
            slave or unit
        """
        last_error = None

        for unit_kw in ("device_id", "slave", "unit"):
            try:
                return func(**kwargs, **{unit_kw: self.unit_id})
            except TypeError as exc:
                last_error = exc

        raise last_error

    def _execute_with_retry(self, func, **kwargs):
        """
        Execute a Modbus transaction with retry.

        If a transaction fails, the driver will try to reconnect before
        the next attempt. This is useful for EMS gateway service also,
        not only for CLI testing.
        """
        self._ensure_connected()

        last_error = None

        for attempt in range(self.retries + 1):
            try:
                response = self._call_with_unit_id(func, **kwargs)

                if response is None:
                    raise RuntimeError("No response from Modbus device")

                if hasattr(response, "isError") and response.isError():
                    raise RuntimeError(f"Modbus error response: {response}")

                return response

            except Exception as exc:
                last_error = exc

                if attempt >= self.retries:
                    raise

                print(
                    f"[WARN] Modbus transaction failed, retrying "
                    f"{attempt + 1}/{self.retries}: {exc}"
                )

                time.sleep(self.retry_delay)

                # Try to refresh TCP connection before next transaction attempt.
                self._reconnect()

        raise RuntimeError(f"Modbus transaction failed: {last_error}")

    def read_holding_registers(self, address: int, count: int) -> List[int]:
        response = self._execute_with_retry(
            self.client.read_holding_registers,
            address=address,
            count=count,
        )
        return list(response.registers)

    def read_input_registers(self, address: int, count: int) -> List[int]:
        response = self._execute_with_retry(
            self.client.read_input_registers,
            address=address,
            count=count,
        )
        return list(response.registers)

    def read_coils(self, address: int, count: int) -> List[bool]:
        response = self._execute_with_retry(
            self.client.read_coils,
            address=address,
            count=count,
        )
        return list(response.bits[:count])

    def read_discrete_inputs(self, address: int, count: int) -> List[bool]:
        response = self._execute_with_retry(
            self.client.read_discrete_inputs,
            address=address,
            count=count,
        )
        return list(response.bits[:count])

    def write_register(self, address: int, value: int):
        """
        Write one holding register.
        Handles signed 16-bit values by converting them to unsigned Modbus register format.
        """
        value_u16 = self.to_u16(value)

        return self._execute_with_retry(
            self.client.write_register,
            address=address,
            value=value_u16,
        )

    def write_registers(self, address: int, values: List[int]):
        values_u16 = [self.to_u16(v) for v in values]

        return self._execute_with_retry(
            self.client.write_registers,
            address=address,
            values=values_u16,
        )

    def write_coil(self, address: int, value: bool):
        return self._execute_with_retry(
            self.client.write_coil,
            address=address,
            value=bool(value),
        )

    @staticmethod
    def to_s16(value: int) -> int:
        """
        Convert unsigned 16-bit Modbus register value to signed int16.
        """
        value = value & 0xFFFF
        if value & 0x8000:
            return value - 0x10000
        return value

    @staticmethod
    def to_u16(value: int) -> int:
        """
        Convert signed Python int to unsigned 16-bit Modbus register value.
        """
        return value & 0xFFFF

    @staticmethod
    def scale(value: int, factor: float, signed: bool = False) -> float:
        if signed:
            value = PcsModbusTcpDriver.to_s16(value)
        return value * factor