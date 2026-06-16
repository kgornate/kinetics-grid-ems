"""Structured query result model for storage log queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

JsonDict = Dict[str, Any]


@dataclass
class LogQueryResult:
    status: str
    rows: List[JsonDict] = field(default_factory=list)
    file: str = ""
    file_name: str = ""
    message: str = ""
    total_rows: int = 0
    filtered_rows: int = 0
    rows_count: int = 0
    limit: int = 100
    offset: int = 0
    filters: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        result = {
            "status": self.status,
            "file": self.file,
            "file_name": self.file_name,
            "total_rows": self.total_rows,
            "filtered_rows": self.filtered_rows,
            "rows_count": self.rows_count,
            "limit": self.limit,
            "offset": self.offset,
            "filters": self.filters,
            "rows": self.rows,
        }
        if self.message:
            result["message"] = self.message
        return result
