import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class StorageLogger:
    """
    EMS Storage Logger

    This logger is storage-independent.
    It can write to:
    - PC local folder during development
    - i.MX93 eMMC path: /home/root/ems_logs_test
    - SD card path: /mnt/ems_sdcard

    Supported asset log formats:
    - Chiller telemetry/events/errors
    - PCS/Inverter telemetry/events/errors

    Folder structure:
        <base_path>/logs/<asset_id>/YYYY-MM-DD.csv
        <base_path>/events/<asset_id>_events.csv
        <base_path>/errors/<asset_id>_errors.csv
        <base_path>/metadata/gateway_info.txt
    """

    def __init__(
        self,
        base_path: str,
        gateway_id: str = "imx93_gateway_1",
        asset_id: str = "chiller_1",
        asset_type: Optional[str] = None,
    ):
        self.base_path = Path(base_path)
        self.gateway_id = gateway_id
        self.asset_id = asset_id
        self.asset_type = (asset_type or self._infer_asset_type(asset_id)).lower()

        self.sequence_no = 0
        self.logger_status = "not_initialized"

        self.chiller_telemetry_header = [
            "timestamp",
            "sequence_no",
            "gateway_id",
            "asset_id",
            "system_on_off",
            "control_mode",
            "set_temperature",
            "outlet_water_temp",
            "return_water_temp",
            "outlet_water_pressure",
            "return_water_pressure",
            "ambient_temp",
            "water_pump_status",
            "compressor_1_status",
            "compressor_2_status",
            "electric_heater_status",
            "condensate_fan_status",
            "modbus_status",
            "logger_status",
        ]

        self.pcs_telemetry_header = [
            "timestamp",
            "sequence_no",
            "gateway_id",
            "asset_id",
            "vendor",
            "comm_status",
            "active_power_kw",
            "reactive_power_kvar",
            "apparent_power_kva",
            "power_factor",
            "frequency_hz",
            "battery_voltage_v",
            "battery_current_a",
            "dc_power_kw",
            "dc_total_current_a",
            "bus_voltage_v",
            "ab_voltage_v",
            "bc_voltage_v",
            "ca_voltage_v",
            "phase_a_voltage_v",
            "phase_b_voltage_v",
            "phase_c_voltage_v",
            "phase_a_current_a",
            "phase_b_current_a",
            "phase_c_current_a",
            "operating_status",
            "operating_status_raw",
            "grid_offgrid_status",
            "grid_offgrid_status_raw",
            "fault_status",
            "igbt_temperature_c",
            "ambient_temperature_c",
            "inductance_temperature_c",
            "error",
            "logger_status",
        ]

        self.chiller_event_header = [
            "timestamp",
            "gateway_id",
            "asset_id",
            "event_type",
            "old_value",
            "new_value",
            "source",
            "status",
            "description",
        ]

        self.pcs_event_header = [
            "timestamp",
            "gateway_id",
            "asset_id",
            "vendor",
            "event_type",
            "command",
            "old_value",
            "new_value",
            "readback_value",
            "source",
            "status",
            "description",
            "error",
        ]

        self.error_header = [
            "timestamp",
            "gateway_id",
            "asset_id",
            "error_type",
            "error_source",
            "description",
        ]

    # -------------------------------------------------
    # Type helpers
    # -------------------------------------------------

    @staticmethod
    def _infer_asset_type(asset_id: str) -> str:
        text = str(asset_id).lower()
        if text.startswith("pcs") or "inverter" in text:
            return "pcs"
        return "chiller"

    def is_pcs_asset(self) -> bool:
        return self.asset_type == "pcs"

    # -------------------------------------------------
    # Path / timestamp helpers
    # -------------------------------------------------

    def get_timestamp(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def get_today_date(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def get_telemetry_dir(self) -> Path:
        return self.base_path / "logs" / self.asset_id

    def get_event_dir(self) -> Path:
        return self.base_path / "events"

    def get_error_dir(self) -> Path:
        return self.base_path / "errors"

    def get_metadata_dir(self) -> Path:
        return self.base_path / "metadata"

    def get_telemetry_file_path(self) -> Path:
        return self.get_telemetry_dir() / f"{self.get_today_date()}.csv"

    def get_event_file_path(self) -> Path:
        return self.get_event_dir() / f"{self.asset_id}_events.csv"

    def get_error_file_path(self) -> Path:
        return self.get_error_dir() / f"{self.asset_id}_errors.csv"

    # -------------------------------------------------
    # Initialization
    # -------------------------------------------------

    def initialize(self) -> bool:
        """
        Create required folders and verify storage write access.
        """
        try:
            self.get_telemetry_dir().mkdir(parents=True, exist_ok=True)
            self.get_event_dir().mkdir(parents=True, exist_ok=True)
            self.get_error_dir().mkdir(parents=True, exist_ok=True)
            self.get_metadata_dir().mkdir(parents=True, exist_ok=True)

            if not self.verify_write_access():
                self.logger_status = "write_access_failed"
                return False

            self.create_metadata_file()
            self.logger_status = "ok"
            return True

        except Exception as error:
            self.logger_status = "init_failed"
            print(f"[LOGGER] Initialization failed: {error}")
            return False

    def verify_write_access(self) -> bool:
        """
        Creates a temporary file to confirm that the storage path is writable.
        """
        try:
            test_file = self.base_path / ".logger_write_test"

            with open(test_file, "w", encoding="utf-8") as file:
                file.write("write_test_ok\n")
                file.flush()
                os.fsync(file.fileno())

            test_file.unlink(missing_ok=True)
            return True

        except Exception as error:
            print(f"[LOGGER] Write access verification failed: {error}")
            return False

    def write_header_if_new_file(self, file_path: Path, header: List[str]) -> None:
        if not file_path.exists() or file_path.stat().st_size == 0:
            with open(file_path, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(header)
                file.flush()
                os.fsync(file.fileno())

    @staticmethod
    def _value(data: Dict[str, Any], key: str, default: Any = "") -> Any:
        value = data.get(key, default)
        if value is None:
            return ""
        return value

    # -------------------------------------------------
    # Telemetry logging
    # -------------------------------------------------

    def log_telemetry(self, telemetry: dict) -> bool:
        """
        Logs one complete telemetry snapshot.

        For chiller assets, this writes the existing chiller CSV format.
        For PCS assets, this writes PCS/Inverter telemetry columns.
        """
        if self.is_pcs_asset():
            return self.log_pcs_telemetry(telemetry)

        return self.log_chiller_telemetry(telemetry)

    def log_chiller_telemetry(self, telemetry: dict) -> bool:
        try:
            file_path = self.get_telemetry_file_path()
            self.write_header_if_new_file(file_path, self.chiller_telemetry_header)

            self.sequence_no += 1

            row = [
                self.get_timestamp(),
                self.sequence_no,
                self.gateway_id,
                self.asset_id,
                telemetry.get("system_on_off", "unknown"),
                telemetry.get("control_mode", "unknown"),
                telemetry.get("set_temperature", "unknown"),
                telemetry.get("outlet_water_temp", "unknown"),
                telemetry.get("return_water_temp", "unknown"),
                telemetry.get("outlet_water_pressure", "unknown"),
                telemetry.get("return_water_pressure", "unknown"),
                telemetry.get("ambient_temp", "unknown"),
                telemetry.get("water_pump_status", "unknown"),
                telemetry.get("compressor_1_status", "unknown"),
                telemetry.get("compressor_2_status", "unknown"),
                telemetry.get("electric_heater_status", "unknown"),
                telemetry.get("condensate_fan_status", "unknown"),
                telemetry.get("modbus_status", "unknown"),
                self.logger_status,
            ]

            with open(file_path, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(row)
                file.flush()
                os.fsync(file.fileno())

            self.logger_status = "ok"
            return True

        except Exception as error:
            self.logger_status = "telemetry_write_failed"
            print(f"[LOGGER] Chiller telemetry logging failed: {error}")
            return False

    def log_pcs_telemetry(self, telemetry: dict) -> bool:
        try:
            file_path = self.get_telemetry_file_path()
            self.write_header_if_new_file(file_path, self.pcs_telemetry_header)

            self.sequence_no += 1

            row = [
                self.get_timestamp(),
                self.sequence_no,
                self.gateway_id,
                self.asset_id,
                self._value(telemetry, "vendor", "unknown"),
                self._value(telemetry, "comm_status", "unknown"),
                self._value(telemetry, "active_power_kw"),
                self._value(telemetry, "reactive_power_kvar"),
                self._value(telemetry, "apparent_power_kva"),
                self._value(telemetry, "power_factor"),
                self._value(telemetry, "frequency_hz"),
                self._value(telemetry, "battery_voltage_v"),
                self._value(telemetry, "battery_current_a"),
                self._value(telemetry, "dc_power_kw"),
                self._value(telemetry, "dc_total_current_a"),
                self._value(telemetry, "bus_voltage_v"),
                self._value(telemetry, "ab_voltage_v"),
                self._value(telemetry, "bc_voltage_v"),
                self._value(telemetry, "ca_voltage_v"),
                self._value(telemetry, "phase_a_voltage_v"),
                self._value(telemetry, "phase_b_voltage_v"),
                self._value(telemetry, "phase_c_voltage_v"),
                self._value(telemetry, "phase_a_current_a"),
                self._value(telemetry, "phase_b_current_a"),
                self._value(telemetry, "phase_c_current_a"),
                self._value(telemetry, "operating_status", "unknown"),
                self._value(telemetry, "operating_status_raw"),
                self._value(telemetry, "grid_offgrid_status", "unknown"),
                self._value(telemetry, "grid_offgrid_status_raw"),
                self._value(telemetry, "fault_status"),
                self._value(telemetry, "igbt_temperature_c"),
                self._value(telemetry, "ambient_temperature_c"),
                self._value(telemetry, "inductance_temperature_c"),
                self._value(telemetry, "error"),
                self.logger_status,
            ]

            with open(file_path, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(row)
                file.flush()
                os.fsync(file.fileno())

            self.logger_status = "ok"
            return True

        except Exception as error:
            self.logger_status = "telemetry_write_failed"
            print(f"[LOGGER] PCS telemetry logging failed: {error}")
            return False

    # -------------------------------------------------
    # Event logging
    # -------------------------------------------------

    def log_event(
        self,
        event_type: str,
        old_value: str = "",
        new_value: str = "",
        source: str = "gateway",
        status: str = "success",
        description: str = "",
        command: str = "",
        readback_value: str = "",
        vendor: str = "",
        error: str = "",
    ) -> bool:
        """
        Logs control commands and important system events.

        Chiller calls can continue using the old argument set.
        PCS calls can additionally pass vendor, command, readback_value, and error.
        """
        if self.is_pcs_asset():
            return self.log_pcs_event(
                event_type=event_type,
                command=command,
                old_value=old_value,
                new_value=new_value,
                readback_value=readback_value,
                source=source,
                status=status,
                description=description,
                vendor=vendor,
                error=error,
            )

        return self.log_chiller_event(
            event_type=event_type,
            old_value=old_value,
            new_value=new_value,
            source=source,
            status=status,
            description=description,
        )

    def log_chiller_event(
        self,
        event_type: str,
        old_value: str = "",
        new_value: str = "",
        source: str = "gateway",
        status: str = "success",
        description: str = "",
    ) -> bool:
        try:
            file_path = self.get_event_file_path()
            self.write_header_if_new_file(file_path, self.chiller_event_header)

            row = [
                self.get_timestamp(),
                self.gateway_id,
                self.asset_id,
                event_type,
                old_value,
                new_value,
                source,
                status,
                description,
            ]

            with open(file_path, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(row)
                file.flush()
                os.fsync(file.fileno())

            return True

        except Exception as error:
            self.logger_status = "event_write_failed"
            print(f"[LOGGER] Chiller event logging failed: {error}")
            return False

    def log_pcs_event(
        self,
        event_type: str,
        command: str = "",
        old_value: str = "",
        new_value: str = "",
        readback_value: str = "",
        source: str = "gateway",
        status: str = "success",
        description: str = "",
        vendor: str = "",
        error: str = "",
    ) -> bool:
        try:
            file_path = self.get_event_file_path()
            self.write_header_if_new_file(file_path, self.pcs_event_header)

            row = [
                self.get_timestamp(),
                self.gateway_id,
                self.asset_id,
                vendor,
                event_type,
                command,
                old_value,
                new_value,
                readback_value,
                source,
                status,
                description,
                error,
            ]

            with open(file_path, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(row)
                file.flush()
                os.fsync(file.fileno())

            return True

        except Exception as error_obj:
            self.logger_status = "event_write_failed"
            print(f"[LOGGER] PCS event logging failed: {error_obj}")
            return False

    # -------------------------------------------------
    # Error logging
    # -------------------------------------------------

    def log_error(
        self,
        error_type: str,
        error_source: str,
        description: str,
    ) -> bool:
        """
        Logs Modbus errors, storage errors, application errors, etc.
        """
        try:
            file_path = self.get_error_file_path()
            self.write_header_if_new_file(file_path, self.error_header)

            row = [
                self.get_timestamp(),
                self.gateway_id,
                self.asset_id,
                error_type,
                error_source,
                description,
            ]

            with open(file_path, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(row)
                file.flush()
                os.fsync(file.fileno())

            return True

        except Exception as error:
            self.logger_status = "error_write_failed"
            print(f"[LOGGER] Error logging failed: {error}")
            return False

    # -------------------------------------------------
    # Metadata / status
    # -------------------------------------------------

    def create_metadata_file(self) -> None:
        metadata_path = self.get_metadata_dir() / "gateway_info.txt"

        existing = ""
        if metadata_path.exists():
            try:
                existing = metadata_path.read_text(encoding="utf-8")
            except Exception:
                existing = ""

        entry = (
            f"gateway_id={self.gateway_id}\n"
            f"asset_id={self.asset_id}\n"
            f"asset_type={self.asset_type}\n"
            f"base_path={self.base_path}\n"
            f"created_at={self.get_timestamp()}\n"
            f"logger_type=storage_independent_csv_logger\n"
            "---\n"
        )

        if f"asset_id={self.asset_id}\n" in existing:
            return

        with open(metadata_path, mode="a", encoding="utf-8") as file:
            file.write(entry)
            file.flush()
            os.fsync(file.fileno())

    def get_status(self) -> dict:
        return {
            "logger_status": self.logger_status,
            "base_path": str(self.base_path),
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "gateway_id": self.gateway_id,
            "sequence_no": self.sequence_no,
            "telemetry_file": str(self.get_telemetry_file_path()),
            "event_file": str(self.get_event_file_path()),
            "error_file": str(self.get_error_file_path()),
        }
