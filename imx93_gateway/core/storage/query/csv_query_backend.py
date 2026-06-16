"""CSV-backed log query backend."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List

from .filter_model import LogFilter
from .result_model import LogQueryResult

JsonDict = Dict[str, Any]


class CSVLogQueryBackend:
    """Apply structured LogFilter objects to CSV log files."""

    @staticmethod
    def _extract_date(timestamp: str) -> str:
        return timestamp[:10] if len(timestamp) >= 10 else ""

    @staticmethod
    def _extract_time(timestamp: str) -> str:
        if "T" in timestamp and len(timestamp) >= 19:
            return timestamp.split("T", 1)[1][:8]
        if " " in timestamp and len(timestamp) >= 19:
            return timestamp.split(" ", 1)[1][:8]
        return ""

    @staticmethod
    def _row_matches_search(row: JsonDict, search: Any) -> bool:
        if search is None:
            return True
        text = str(search).strip().lower()
        if not text:
            return True
        return text in " ".join(str(value) for value in row.values()).lower()

    @staticmethod
    def _apply_field_selection(rows: List[JsonDict], fields: Any) -> List[JsonDict]:
        if not fields:
            return rows
        return [{field: row.get(field, "") for field in fields if field in row} for row in rows]

    @staticmethod
    def _matches_exact_filters(row: JsonDict, exact_filters: JsonDict) -> bool:
        for key, expected_value in (exact_filters or {}).items():
            if expected_value is None:
                continue
            expected = str(expected_value).strip()
            if not expected or expected.lower() == "all":
                continue
            actual = str(row.get(key, "")).strip()
            if actual.lower() != expected.lower():
                return False
        return True

    def _filter_rows(self, rows: List[JsonDict], log_filter: LogFilter) -> List[JsonDict]:
        filtered: List[JsonDict] = []
        for row in rows:
            timestamp = str(row.get("timestamp", ""))
            if log_filter.date and self._extract_date(timestamp) != log_filter.date:
                continue
            row_time = self._extract_time(timestamp)
            if log_filter.start_time and row_time and row_time < log_filter.start_time:
                continue
            if log_filter.end_time and row_time and row_time > log_filter.end_time:
                continue
            if not self._matches_exact_filters(row, log_filter.exact_filters):
                continue
            if not self._row_matches_search(row, log_filter.search):
                continue
            filtered.append(row)
        return filtered

    def query(self, file_path: Path, log_filter: LogFilter) -> JsonDict:
        if not file_path.exists():
            return LogQueryResult(
                status="error",
                message=f"Log file not found: {file_path.name}",
                file=str(file_path),
                rows_count=0,
                limit=log_filter.limit,
                offset=log_filter.offset,
                filters=log_filter.to_response_dict(),
            ).to_dict()

        try:
            with open(file_path, mode="r", encoding="utf-8", newline="") as file:
                all_rows = list(csv.DictReader(file))

            filtered_rows = self._filter_rows(all_rows, log_filter)
            if log_filter.order == "desc":
                ordered_rows = list(reversed(filtered_rows))
            else:
                ordered_rows = filtered_rows

            start = log_filter.offset
            end = start + log_filter.limit if log_filter.limit else None
            page_rows = ordered_rows[start:end]
            page_rows = self._apply_field_selection(page_rows, log_filter.fields)

            return LogQueryResult(
                status="ok",
                file=str(file_path),
                file_name=file_path.name,
                total_rows=len(all_rows),
                filtered_rows=len(filtered_rows),
                rows_count=len(page_rows),
                rows=page_rows,
                limit=log_filter.limit,
                offset=log_filter.offset,
                filters=log_filter.to_response_dict(),
            ).to_dict()
        except Exception as error:
            return LogQueryResult(
                status="error",
                message=str(error),
                file=str(file_path),
                rows_count=0,
                limit=log_filter.limit,
                offset=log_filter.offset,
                filters=log_filter.to_response_dict(),
            ).to_dict()
