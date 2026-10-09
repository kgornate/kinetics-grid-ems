from __future__ import annotations

import json
import logging
import sqlite3
from collections import OrderedDict
from pathlib import Path
from typing import Any

from .config import FastBESSUploadConfig, UploaderConfig

LOG = logging.getLogger(__name__)


def _safe_value(value: Any) -> Any:
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)


class FastBESSAdapter:
    def __init__(self, config: UploaderConfig) -> None:
        self.root_config = config
        self.config: FastBESSUploadConfig = config.fast_bess_upload

    def _connect_ro(self) -> sqlite3.Connection:
        path = Path(self.config.db_path)
        if not path.exists():
            raise FileNotFoundError(f"fast BESS DB not found: {path}")
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def fetch_records_after(self, after_epoch_ms: int) -> tuple[list[dict[str, Any]], int]:
        conn = self._connect_ro()
        try:
            rows = conn.execute(
                """
                SELECT * FROM fast_bess_samples
                WHERE timestamp_epoch_ms > ?
                ORDER BY timestamp_epoch_ms ASC, source_id ASC, id ASC
                LIMIT ?
                """,
                (int(after_epoch_ms), int(self.config.max_source_rows_per_cycle)),
            ).fetchall()
        finally:
            conn.close()
        grouped: OrderedDict[int, dict[str, Any]] = OrderedDict()
        max_ts = int(after_epoch_ms)
        for row in rows:
            ts = int(row["timestamp_epoch_ms"])
            max_ts = max(max_ts, ts)
            record = grouped.setdefault(ts, {"ts": ts, "values": {}})
            values = record["values"]
            bess_id = str(row["bess_id"] or row["source_id"] or "bess").strip()
            quality = row["quality"]
            pcs_values = json.loads(row["pcs_values_json"] or "{}")
            bms_values = json.loads(row["bms_values_json"] or "{}")
            self._merge_values(values, bess_id, "pcs", pcs_values)
            self._merge_values(values, bess_id, "bms", bms_values)
            if self.config.include_quality_metadata:
                values[self._key(bess_id, "meta", "quality")] = quality
                values[self._key(bess_id, "meta", "max_data_age_ms")] = row["max_data_age_ms"]
            if self.config.include_profile_metadata:
                values[self._key(bess_id, "meta", "profile_name")] = row["profile_name"]
                values[self._key(bess_id, "meta", "selected_signal_count")] = row["selected_signal_count"]
                values[self._key(bess_id, "meta", "good_signal_count")] = row["good_signal_count"]
                values[self._key(bess_id, "meta", "bad_signal_count")] = row["bad_signal_count"]
        return list(grouped.values()), max_ts

    def _merge_values(self, target: dict[str, Any], bess_id: str, asset: str, values: dict[str, Any]) -> None:
        for signal, value in values.items():
            target[self._key(bess_id, asset, str(signal))] = _safe_value(value)

    def _key(self, bess_id: str, asset: str, signal: str) -> str:
        raw = self.config.value_key_format.format(bess_id=bess_id, asset=asset, signal=signal)
        key = f"{self.config.key_prefix}{raw}"
        return self.root_config.key_aliases.get(key, key)
