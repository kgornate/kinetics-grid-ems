"""Structured log filter model for telemetry, event, and error queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

JsonDict = Dict[str, Any]


TELEMETRY_EXACT_FILTER_KEYS = {
    "modbus_status",
    "logger_status",
    "vendor",
    "comm_status",
    "operating_status",
    "fault_status",
    "communication_status",
    "bcu_state",
    "current_state",
}

EVENT_EXACT_FILTER_KEYS = {
    "event_type",
    "status",
    "source",
    "vendor",
    "command",
}

ERROR_EXACT_FILTER_KEYS = {
    "error_type",
    "error_source",
    "source",
}


@dataclass(frozen=True)
class LogFilter:
    """Common filter model used by HTTP APIs and storage backends."""

    log_type: str
    asset_id: Optional[str] = None
    date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    fields: Optional[List[str]] = None
    exact_filters: JsonDict = field(default_factory=dict)
    search: Optional[str] = None
    limit: int = 100
    offset: int = 0
    order: str = "asc"

    @staticmethod
    def _first(query: Mapping[str, Any], key: str, default: Any = None) -> Any:
        value = query.get(key, default)
        if isinstance(value, list):
            return value[0] if value else default
        return value

    @staticmethod
    def sanitize_limit(value: Optional[Any], default: int = 100, maximum: int = 500) -> int:
        try:
            limit = int(value)
        except Exception:
            limit = default
        if limit <= 0:
            limit = default
        return min(limit, maximum)

    @staticmethod
    def sanitize_offset(value: Optional[Any]) -> int:
        try:
            offset = int(value)
        except Exception:
            offset = 0
        return max(offset, 0)

    @staticmethod
    def parse_fields(value: Optional[Any]) -> Optional[List[str]]:
        if value is None:
            return None
        if isinstance(value, list):
            text = ",".join(str(item) for item in value)
        else:
            text = str(value)
        fields = [item.strip() for item in text.split(",") if item.strip()]
        return fields or None

    @staticmethod
    def normalize_time(value: Optional[Any]) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if len(text) == 5 and text[2] == ":":
            return f"{text}:00"
        return text

    @staticmethod
    def validate_date(value: Optional[Any]) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if len(text) != 10 or text[4] != "-" or text[7] != "-":
            raise ValueError("date must be in YYYY-MM-DD format")
        y, m, d = text.split("-")
        if not (y.isdigit() and m.isdigit() and d.isdigit()):
            raise ValueError("date must be in YYYY-MM-DD format")
        return text

    @classmethod
    def from_http_query(
        cls,
        *,
        log_type: str,
        query: Mapping[str, Any],
        asset_id: Optional[Any] = None,
        max_rows: int = 500,
    ) -> "LogFilter":
        normalized_type = str(log_type or "").strip().lower()
        exact_keys = {
            "telemetry": TELEMETRY_EXACT_FILTER_KEYS,
            "events": EVENT_EXACT_FILTER_KEYS,
            "errors": ERROR_EXACT_FILTER_KEYS,
        }.get(normalized_type, set())

        exact_filters: JsonDict = {}
        for key in exact_keys:
            value = cls._first(query, key)
            if value is not None:
                exact_filters[key] = value

        # Backward-compatible alias: /api/logs/errors?source=modbus
        # maps to the error_source column when error_source is absent.
        if normalized_type == "errors":
            if "error_source" not in exact_filters and cls._first(query, "source") is not None:
                exact_filters["error_source"] = cls._first(query, "source")
            exact_filters.pop("source", None)

        order = str(cls._first(query, "order", "asc") or "asc").strip().lower()
        if order not in {"asc", "desc"}:
            order = "asc"

        return cls(
            log_type=normalized_type,
            asset_id=str(asset_id).strip() if asset_id else None,
            date=cls.validate_date(cls._first(query, "date")),
            start_time=cls.normalize_time(cls._first(query, "start_time")),
            end_time=cls.normalize_time(cls._first(query, "end_time")),
            fields=cls.parse_fields(cls._first(query, "fields")),
            exact_filters=exact_filters,
            search=str(cls._first(query, "search")).strip() if cls._first(query, "search") is not None else None,
            limit=cls.sanitize_limit(cls._first(query, "limit", 100), maximum=max_rows),
            offset=cls.sanitize_offset(cls._first(query, "offset", 0)),
            order=order,
        )

    def to_response_dict(self) -> JsonDict:
        return {
            "log_type": self.log_type,
            "asset_id": self.asset_id,
            "date": self.date,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "fields": self.fields,
            "exact_filters": dict(self.exact_filters),
            "search": self.search,
            "limit": self.limit,
            "offset": self.offset,
            "order": self.order,
        }
