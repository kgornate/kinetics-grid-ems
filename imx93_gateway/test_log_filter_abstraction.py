"""Log query/filter abstraction checks.

Run from imx93_gateway:
    python3 test_log_filter_abstraction.py
"""

import csv
import tempfile
import unittest
from pathlib import Path

from core.storage.query import LogFilter
from services.log_query_service import LogQueryService


class LogFilterAbstractionTests(unittest.TestCase):
    def write_csv(self, path: Path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def test_telemetry_date_time_field_search_and_exact_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            rows = [
                {
                    "timestamp": "2026-06-12T09:59:59+05:30",
                    "active_power_kw": "5.0",
                    "dc_voltage_v": "620",
                    "comm_status": "online",
                    "vendor": "njoy",
                    "message": "before window",
                },
                {
                    "timestamp": "2026-06-12T10:15:00+05:30",
                    "active_power_kw": "10.0",
                    "dc_voltage_v": "640",
                    "comm_status": "online",
                    "vendor": "njoy",
                    "message": "inside target window",
                },
                {
                    "timestamp": "2026-06-12T10:30:00+05:30",
                    "active_power_kw": "11.0",
                    "dc_voltage_v": "642",
                    "comm_status": "offline",
                    "vendor": "njoy",
                    "message": "wrong status",
                },
                {
                    "timestamp": "2026-06-12T12:00:00+05:30",
                    "active_power_kw": "12.0",
                    "dc_voltage_v": "644",
                    "comm_status": "online",
                    "vendor": "njoy",
                    "message": "after window",
                },
            ]
            self.write_csv(base / "logs" / "pcs_1" / "2026-06-12.csv", rows)
            query = LogQueryService(base_path=str(base), asset_id="pcs_1", max_rows=500)

            result = query.get_telemetry_logs(
                asset_id="pcs_1",
                date="2026-06-12",
                start_time="10:00",
                end_time="10:45:00",
                fields="timestamp,active_power_kw,comm_status",
                comm_status="online",
                search="target",
                limit=10,
            )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["filtered_rows"], 1)
            self.assertEqual(result["rows_count"], 1)
            self.assertEqual(
                result["rows"][0],
                {
                    "timestamp": "2026-06-12T10:15:00+05:30",
                    "active_power_kw": "10.0",
                    "comm_status": "online",
                },
            )
            self.assertEqual(result["filters"]["fields"], ["timestamp", "active_power_kw", "comm_status"])
            self.assertEqual(result["filters"]["exact_filters"]["comm_status"], "online")

    def test_structured_log_filter_supports_order_and_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            rows = [
                {"timestamp": "2026-06-12T10:00:00+05:30", "value": "1", "comm_status": "online"},
                {"timestamp": "2026-06-12T10:01:00+05:30", "value": "2", "comm_status": "online"},
                {"timestamp": "2026-06-12T10:02:00+05:30", "value": "3", "comm_status": "online"},
            ]
            self.write_csv(base / "logs" / "pcs_1" / "2026-06-12.csv", rows)
            query = LogQueryService(base_path=str(base), asset_id="pcs_1", max_rows=500)
            log_filter = LogFilter(
                log_type="telemetry",
                asset_id="pcs_1",
                date="2026-06-12",
                limit=1,
                offset=1,
                order="desc",
            )

            result = query.query_logs(log_filter)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["rows_count"], 1)
            self.assertEqual(result["rows"][0]["value"], "2")
            self.assertEqual(result["filters"]["order"], "desc")
            self.assertEqual(result["filters"]["offset"], 1)

    def test_event_and_error_filters_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.write_csv(
                base / "events" / "pcs_1_events.csv",
                [
                    {
                        "timestamp": "2026-06-12T10:00:00+05:30",
                        "event_type": "PCS_ACTIVE_POWER_WRITE",
                        "status": "success",
                        "source": "command",
                        "command": "PCS_SET_ACTIVE_POWER",
                        "description": "setpoint accepted",
                    },
                    {
                        "timestamp": "2026-06-12T10:05:00+05:30",
                        "event_type": "PCS_ACTIVE_POWER_WRITE",
                        "status": "failed",
                        "source": "command",
                        "command": "PCS_SET_ACTIVE_POWER",
                        "description": "setpoint rejected",
                    },
                ],
            )
            self.write_csv(
                base / "errors" / "bms_1_errors.csv",
                [
                    {
                        "timestamp": "2026-06-12T10:00:00+05:30",
                        "error_type": "communication",
                        "error_source": "modbus",
                        "description": "timeout",
                    },
                    {
                        "timestamp": "2026-06-12T10:10:00+05:30",
                        "error_type": "storage",
                        "error_source": "csv",
                        "description": "disk warning",
                    },
                ],
            )
            query = LogQueryService(base_path=str(base), asset_id="pcs_1", max_rows=500)

            events = query.get_event_logs(
                asset_id="pcs_1",
                event_type="PCS_ACTIVE_POWER_WRITE",
                status="success",
                fields="timestamp,event_type,status,command",
            )
            self.assertEqual(events["status"], "ok")
            self.assertEqual(events["filtered_rows"], 1)
            self.assertEqual(events["rows"][0]["status"], "success")
            self.assertEqual(set(events["rows"][0].keys()), {"timestamp", "event_type", "status", "command"})

            errors = query.get_error_logs(
                asset_id="bms_1",
                error_type="communication",
                error_source="modbus",
                search="timeout",
            )
            self.assertEqual(errors["status"], "ok")
            self.assertEqual(errors["filtered_rows"], 1)
            self.assertEqual(errors["rows"][0]["description"], "timeout")

    def test_http_query_filter_model_preserves_source_alias_for_errors(self):
        query = {
            "asset_id": ["bms_1"],
            "source": ["modbus"],
            "limit": ["20"],
            "fields": ["timestamp,error_type,error_source"],
        }
        log_filter = LogFilter.from_http_query(log_type="errors", query=query, asset_id="bms_1")

        self.assertEqual(log_filter.asset_id, "bms_1")
        self.assertEqual(log_filter.exact_filters["error_source"], "modbus")
        self.assertEqual(log_filter.fields, ["timestamp", "error_type", "error_source"])
        self.assertEqual(log_filter.limit, 20)


if __name__ == "__main__":
    unittest.main()
