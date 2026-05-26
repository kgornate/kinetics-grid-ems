import csv
import os
from datetime import datetime
from pathlib import Path


class StorageLogger:
    """
    EMS Storage Logger

    This logger is storage-independent.
    It can write to:
    - PC local folder during development
    - i.MX93 eMMC path: /home/root/ems_logs_test
    - SD card path: /mnt/ems_sdcard

    The logger does not directly access eMMC/SD hardware.
    It writes files to a mounted filesystem path.
    Linux kernel + filesystem handle actual storage writes.
    """

    def __init__(
        self,
        base_path: str,
        gateway_id: str = "imx93_gateway_1",
        asset_id: str = "chiller_1",
    ):
        self.base_path = Path(base_path)
        self.gateway_id = gateway_id
        self.asset_id = asset_id

        self.sequence_no = 0
        self.logger_status = "not_initialized"

        self.telemetry_header = [
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

        self.event_header = [
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

        self.error_header = [
            "timestamp",
            "gateway_id",
            "asset_id",
            "error_type",
            "error_source",
            "description",
        ]

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

    def write_header_if_new_file(self, file_path: Path, header: list) -> None:
        if not file_path.exists() or file_path.stat().st_size == 0:
            with open(file_path, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(header)
                file.flush()
                os.fsync(file.fileno())

    def log_telemetry(self, telemetry: dict) -> bool:
        """
        Logs one complete chiller telemetry snapshot.
        """
        try:
            file_path = self.get_telemetry_file_path()
            self.write_header_if_new_file(file_path, self.telemetry_header)

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
            print(f"[LOGGER] Telemetry logging failed: {error}")
            return False

    def log_event(
        self,
        event_type: str,
        old_value: str = "",
        new_value: str = "",
        source: str = "gateway",
        status: str = "success",
        description: str = "",
    ) -> bool:
        """
        Logs control commands and important system events.
        Example:
        - SET_TEMPERATURE_CHANGED
        - SYSTEM_ON_COMMAND
        - CONTROL_MODE_CHANGED
        """
        try:
            file_path = self.get_event_file_path()
            self.write_header_if_new_file(file_path, self.event_header)

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
            print(f"[LOGGER] Event logging failed: {error}")
            return False

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

    def create_metadata_file(self) -> None:
        metadata_path = self.get_metadata_dir() / "gateway_info.txt"

        with open(metadata_path, mode="w", encoding="utf-8") as file:
            file.write(f"gateway_id={self.gateway_id}\n")
            file.write(f"asset_id={self.asset_id}\n")
            file.write(f"base_path={self.base_path}\n")
            file.write(f"created_at={self.get_timestamp()}\n")
            file.write("logger_type=storage_independent_csv_logger\n")
            file.flush()
            os.fsync(file.fileno())

    def get_status(self) -> dict:
        return {
            "logger_status": self.logger_status,
            "base_path": str(self.base_path),
            "asset_id": self.asset_id,
            "gateway_id": self.gateway_id,
            "sequence_no": self.sequence_no,
        }