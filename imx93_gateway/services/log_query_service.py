"""
Log Query Service for i.MX93 EMS Gateway.

Purpose:
- Read telemetry, event, and error CSV logs from eMMC/SD card.
- Provide structured data to the HTTP Log API server.
- Support multiple assets:
    - chiller_1
    - pcs_1
- Support date/time filtering, field selection, status filtering, and search.
- Keep log reading separate from Modbus polling and storage writing.

This service is read-only.
It does not delete, modify, or rewrite logs.
"""

import csv
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional


class LogQueryService:
    def __init__(
        self,
        base_path: str,
        asset_id: str = "chiller_1",
        max_rows: int = 500,
    ):
        self.base_path = Path(base_path)
        self.asset_id = asset_id
        self.max_rows = int(max_rows)

    # -------------------------------------------------
    # Asset helpers
    # -------------------------------------------------

    def _resolve_asset_id(self, asset_id: Optional[Any] = None) -> str:
        value = str(asset_id or self.asset_id).strip()

        if not value:
            value = self.asset_id

        # Basic path traversal protection.
        if "/" in value or "\\" in value or ".." in value:
            raise ValueError(f"Invalid asset_id: {value}")

        return value

    # -------------------------------------------------
    # Path helpers
    # -------------------------------------------------

    def telemetry_dir(self, asset_id: Optional[Any] = None) -> Path:
        resolved_asset_id = self._resolve_asset_id(asset_id)
        return self.base_path / "logs" / resolved_asset_id

    def events_file(self, asset_id: Optional[Any] = None) -> Path:
        resolved_asset_id = self._resolve_asset_id(asset_id)
        return self.base_path / "events" / f"{resolved_asset_id}_events.csv"

    def errors_file(self, asset_id: Optional[Any] = None) -> Path:
        resolved_asset_id = self._resolve_asset_id(asset_id)
        return self.base_path / "errors" / f"{resolved_asset_id}_errors.csv"

    def metadata_file(self) -> Path:
        return self.base_path / "metadata" / "gateway_info.txt"

    def telemetry_file_for_date(self, date_str: str, asset_id: Optional[Any] = None) -> Path:
        safe_date = self._validate_date_string(date_str)
        return self.telemetry_dir(asset_id) / f"{safe_date}.csv"

    # -------------------------------------------------
    # Validation helpers
    # -------------------------------------------------

    @staticmethod
    def _validate_date_string(date_str: str) -> str:
        if not date_str:
            raise ValueError("date parameter is required")

        if len(date_str) != 10:
            raise ValueError("date must be in YYYY-MM-DD format")

        if date_str[4] != "-" or date_str[7] != "-":
            raise ValueError("date must be in YYYY-MM-DD format")

        y, m, d = date_str.split("-")

        if not (y.isdigit() and m.isdigit() and d.isdigit()):
            raise ValueError("date must be in YYYY-MM-DD format")

        return date_str

    def _sanitize_limit(self, limit: Optional[Any]) -> int:
        try:
            value = int(limit)
        except Exception:
            value = 100

        if value <= 0:
            value = 100

        if value > self.max_rows:
            value = self.max_rows

        return value

    @staticmethod
    def _parse_fields(fields: Optional[Any]) -> Optional[List[str]]:
        if fields is None:
            return None

        if isinstance(fields, list):
            fields_text = ",".join([str(item) for item in fields])
        else:
            fields_text = str(fields)

        selected = [
            item.strip()
            for item in fields_text.split(",")
            if item.strip()
        ]

        return selected if selected else None

    @staticmethod
    def _normalize_time_string(value: Optional[Any]) -> Optional[str]:
        if value is None:
            return None

        text = str(value).strip()

        if not text:
            return None

        if len(text) == 5 and text[2] == ":":
            return f"{text}:00"

        if len(text) == 8 and text[2] == ":" and text[5] == ":":
            return text

        return text

    @staticmethod
    def _extract_date(timestamp: str) -> str:
        if len(timestamp) >= 10:
            return timestamp[:10]

        return ""

    @staticmethod
    def _extract_time(timestamp: str) -> str:
        if "T" in timestamp and len(timestamp) >= 19:
            return timestamp.split("T", 1)[1][:8]

        if " " in timestamp and len(timestamp) >= 19:
            return timestamp.split(" ", 1)[1][:8]

        return ""

    @staticmethod
    def _row_matches_search(row: Dict[str, Any], search: Optional[Any]) -> bool:
        if search is None:
            return True

        search_text = str(search).strip().lower()

        if not search_text:
            return True

        row_text = " ".join([str(value) for value in row.values()]).lower()
        return search_text in row_text

    @staticmethod
    def _apply_field_selection(
        rows: List[Dict[str, Any]],
        fields: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        if not fields:
            return rows

        selected_rows: List[Dict[str, Any]] = []

        for row in rows:
            selected_rows.append(
                {
                    field: row.get(field, "")
                    for field in fields
                    if field in row
                }
            )

        return selected_rows

    def _filter_rows(
        self,
        rows: List[Dict[str, Any]],
        date: Optional[Any] = None,
        start_time: Optional[Any] = None,
        end_time: Optional[Any] = None,
        exact_filters: Optional[Dict[str, Any]] = None,
        search: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        date_text = str(date).strip() if date else None
        start_text = self._normalize_time_string(start_time)
        end_text = self._normalize_time_string(end_time)
        exact_filters = exact_filters or {}

        filtered: List[Dict[str, Any]] = []

        for row in rows:
            timestamp = str(row.get("timestamp", ""))

            if date_text:
                if self._extract_date(timestamp) != date_text:
                    continue

            row_time = self._extract_time(timestamp)

            if start_text and row_time and row_time < start_text:
                continue

            if end_text and row_time and row_time > end_text:
                continue

            matched = True

            for key, expected_value in exact_filters.items():
                if expected_value is None:
                    continue

                expected_text = str(expected_value).strip()

                if not expected_text or expected_text.lower() == "all":
                    continue

                actual_text = str(row.get(key, "")).strip()

                if actual_text.lower() != expected_text.lower():
                    matched = False
                    break

            if not matched:
                continue

            if not self._row_matches_search(row, search):
                continue

            filtered.append(row)

        return filtered

    # -------------------------------------------------
    # CSV helpers
    # -------------------------------------------------

    def _read_csv_filtered(
        self,
        file_path: Path,
        limit: Optional[Any] = 100,
        date: Optional[Any] = None,
        start_time: Optional[Any] = None,
        end_time: Optional[Any] = None,
        fields: Optional[Any] = None,
        exact_filters: Optional[Dict[str, Any]] = None,
        search: Optional[Any] = None,
    ) -> Dict[str, Any]:
        limit_value = self._sanitize_limit(limit)
        selected_fields = self._parse_fields(fields)

        if not file_path.exists():
            return {
                "status": "error",
                "message": f"Log file not found: {file_path.name}",
                "file": str(file_path),
                "rows_count": 0,
                "rows": [],
            }

        try:
            with open(file_path, mode="r", encoding="utf-8", newline="") as file:
                reader = csv.DictReader(file)
                all_rows = list(reader)

            filtered_rows = self._filter_rows(
                rows=all_rows,
                date=date,
                start_time=start_time,
                end_time=end_time,
                exact_filters=exact_filters,
                search=search,
            )

            tail_rows = filtered_rows[-limit_value:] if limit_value else filtered_rows
            tail_rows = self._apply_field_selection(tail_rows, selected_fields)

            return {
                "status": "ok",
                "file": str(file_path),
                "file_name": file_path.name,
                "total_rows": len(all_rows),
                "filtered_rows": len(filtered_rows),
                "rows_count": len(tail_rows),
                "limit": limit_value,
                "filters": {
                    "date": date,
                    "start_time": start_time,
                    "end_time": end_time,
                    "fields": selected_fields,
                    "exact_filters": exact_filters or {},
                    "search": search,
                },
                "rows": tail_rows,
            }

        except Exception as error:
            return {
                "status": "error",
                "message": str(error),
                "file": str(file_path),
                "rows_count": 0,
                "rows": [],
            }

    # -------------------------------------------------
    # Size helpers
    # -------------------------------------------------

    @staticmethod
    def _file_size(path: Path) -> int:
        try:
            if path.exists() and path.is_file():
                return path.stat().st_size
        except Exception:
            pass

        return 0

    @staticmethod
    def _directory_size(path: Path) -> int:
        total = 0

        try:
            if not path.exists():
                return 0

            for root, _, files in os.walk(path):
                for file_name in files:
                    file_path = Path(root) / file_name
                    try:
                        total += file_path.stat().st_size
                    except Exception:
                        pass

        except Exception:
            return 0

        return total

    # -------------------------------------------------
    # Public APIs
    # -------------------------------------------------

    def list_assets(self) -> Dict[str, Any]:
        assets = set()

        logs_dir = self.base_path / "logs"
        events_dir = self.base_path / "events"
        errors_dir = self.base_path / "errors"

        if logs_dir.exists():
            for path in logs_dir.iterdir():
                if path.is_dir():
                    assets.add(path.name)

        if events_dir.exists():
            for path in events_dir.glob("*_events.csv"):
                assets.add(path.name.replace("_events.csv", ""))

        if errors_dir.exists():
            for path in errors_dir.glob("*_errors.csv"):
                assets.add(path.name.replace("_errors.csv", ""))

        if not assets:
            assets.add(self.asset_id)

        ordered_assets = sorted(assets)

        return {
            "status": "ok",
            "base_path": str(self.base_path),
            "assets_count": len(ordered_assets),
            "assets": ordered_assets,
            "default_asset_id": self.asset_id,
        }

    def get_storage_status(self, asset_id: Optional[Any] = None) -> Dict[str, Any]:
        resolved_asset_id = self._resolve_asset_id(asset_id)
        exists = self.base_path.exists()

        total_bytes = 0
        used_bytes = 0
        free_bytes = 0

        try:
            usage = shutil.disk_usage(str(self.base_path if exists else "/"))
            total_bytes = usage.total
            used_bytes = usage.used
            free_bytes = usage.free
        except Exception:
            pass

        telemetry_files_response = self.list_telemetry_files(asset_id=resolved_asset_id)
        telemetry_files = telemetry_files_response.get("files", [])

        latest_telemetry_file = telemetry_files[0] if telemetry_files else None

        telemetry_bytes = self._directory_size(self.telemetry_dir(resolved_asset_id))
        events_bytes = self._file_size(self.events_file(resolved_asset_id))
        errors_bytes = self._file_size(self.errors_file(resolved_asset_id))
        metadata_bytes = self._file_size(self.metadata_file())
        log_total_bytes = self._directory_size(self.base_path)

        return {
            "status": "ok",
            "base_path": str(self.base_path),
            "asset_id": resolved_asset_id,
            "exists": exists,
            "telemetry_dir": str(self.telemetry_dir(resolved_asset_id)),
            "telemetry_dir_exists": self.telemetry_dir(resolved_asset_id).exists(),
            "events_file": str(self.events_file(resolved_asset_id)),
            "events_file_exists": self.events_file(resolved_asset_id).exists(),
            "errors_file": str(self.errors_file(resolved_asset_id)),
            "errors_file_exists": self.errors_file(resolved_asset_id).exists(),
            "metadata_file": str(self.metadata_file()),
            "metadata_file_exists": self.metadata_file().exists(),
            "telemetry_files_count": len(telemetry_files),
            "telemetry_files": telemetry_files,
            "latest_telemetry_file": latest_telemetry_file,
            "disk_total_bytes": total_bytes,
            "disk_used_bytes": used_bytes,
            "disk_free_bytes": free_bytes,
            "log_total_bytes": log_total_bytes,
            "telemetry_log_bytes": telemetry_bytes,
            "event_log_bytes": events_bytes,
            "error_log_bytes": errors_bytes,
            "metadata_bytes": metadata_bytes,
        }

    def list_telemetry_files(self, asset_id: Optional[Any] = None) -> Dict[str, Any]:
        resolved_asset_id = self._resolve_asset_id(asset_id)
        directory = self.telemetry_dir(resolved_asset_id)

        if not directory.exists():
            return {
                "status": "error",
                "asset_id": resolved_asset_id,
                "message": "Telemetry log directory not found",
                "directory": str(directory),
                "files_count": 0,
                "files": [],
            }

        files = sorted(
            [path.name for path in directory.glob("*.csv")],
            reverse=True,
        )

        return {
            "status": "ok",
            "asset_id": resolved_asset_id,
            "directory": str(directory),
            "files_count": len(files),
            "files": files,
        }

    def get_telemetry_logs(
        self,
        date: str,
        limit: Optional[Any] = 100,
        start_time: Optional[Any] = None,
        end_time: Optional[Any] = None,
        fields: Optional[Any] = None,
        modbus_status: Optional[Any] = None,
        logger_status: Optional[Any] = None,
        search: Optional[Any] = None,
        asset_id: Optional[Any] = None,
        vendor: Optional[Any] = None,
        comm_status: Optional[Any] = None,
        operating_status: Optional[Any] = None,
        fault_status: Optional[Any] = None,
    ) -> Dict[str, Any]:
        resolved_asset_id = self._resolve_asset_id(asset_id)
        file_path = self.telemetry_file_for_date(date, asset_id=resolved_asset_id)

        response = self._read_csv_filtered(
            file_path=file_path,
            limit=limit,
            date=None,
            start_time=start_time,
            end_time=end_time,
            fields=fields,
            exact_filters={
                "modbus_status": modbus_status,
                "logger_status": logger_status,
                "vendor": vendor,
                "comm_status": comm_status,
                "operating_status": operating_status,
                "fault_status": fault_status,
            },
            search=search,
        )

        response["log_type"] = "telemetry"
        response["asset_id"] = resolved_asset_id
        response["date"] = date
        return response

    def get_event_logs(
        self,
        limit: Optional[Any] = 100,
        date: Optional[Any] = None,
        start_time: Optional[Any] = None,
        end_time: Optional[Any] = None,
        event_type: Optional[Any] = None,
        status: Optional[Any] = None,
        source: Optional[Any] = None,
        search: Optional[Any] = None,
        fields: Optional[Any] = None,
        asset_id: Optional[Any] = None,
        vendor: Optional[Any] = None,
        command: Optional[Any] = None,
    ) -> Dict[str, Any]:
        resolved_asset_id = self._resolve_asset_id(asset_id)

        response = self._read_csv_filtered(
            file_path=self.events_file(resolved_asset_id),
            limit=limit,
            date=date,
            start_time=start_time,
            end_time=end_time,
            fields=fields,
            exact_filters={
                "event_type": event_type,
                "status": status,
                "source": source,
                "vendor": vendor,
                "command": command,
            },
            search=search,
        )

        response["log_type"] = "events"
        response["asset_id"] = resolved_asset_id
        return response

    def get_error_logs(
        self,
        limit: Optional[Any] = 100,
        date: Optional[Any] = None,
        start_time: Optional[Any] = None,
        end_time: Optional[Any] = None,
        error_type: Optional[Any] = None,
        error_source: Optional[Any] = None,
        search: Optional[Any] = None,
        fields: Optional[Any] = None,
        asset_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        resolved_asset_id = self._resolve_asset_id(asset_id)

        response = self._read_csv_filtered(
            file_path=self.errors_file(resolved_asset_id),
            limit=limit,
            date=date,
            start_time=start_time,
            end_time=end_time,
            fields=fields,
            exact_filters={
                "error_type": error_type,
                "error_source": error_source,
            },
            search=search,
        )

        response["log_type"] = "errors"
        response["asset_id"] = resolved_asset_id
        return response

    def get_metadata(self) -> Dict[str, Any]:
        file_path = self.metadata_file()

        if not file_path.exists():
            return {
                "status": "error",
                "message": "Metadata file not found",
                "file": str(file_path),
                "metadata": {},
            }

        metadata: Dict[str, str] = {}

        try:
            with open(file_path, mode="r", encoding="utf-8") as file:
                for line in file:
                    line = line.strip()

                    if not line or "=" not in line:
                        continue

                    key, value = line.split("=", 1)
                    metadata[key.strip()] = value.strip()

            return {
                "status": "ok",
                "file": str(file_path),
                "metadata": metadata,
            }

        except Exception as error:
            return {
                "status": "error",
                "message": str(error),
                "file": str(file_path),
                "metadata": {},
            }

    def get_telemetry_csv_download_path(self, date: str, asset_id: Optional[Any] = None) -> Path:
        resolved_asset_id = self._resolve_asset_id(asset_id)
        file_path = self.telemetry_file_for_date(date, asset_id=resolved_asset_id)

        if not file_path.exists():
            raise FileNotFoundError(
                f"Telemetry CSV not found for asset_id={resolved_asset_id}, date={date}"
            )

        return file_path
