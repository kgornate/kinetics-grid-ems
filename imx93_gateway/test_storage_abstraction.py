"""Storage abstraction checks.

Run from imx93_gateway:
    python3 test_storage_abstraction.py
"""

import tempfile
import unittest
from pathlib import Path

from core.storage import StorageManager, TelemetryStore, EventStore, ErrorStore, StorageStatus
from services.log_query_service import LogQueryService


class StorageAbstractionTests(unittest.TestCase):
    def test_storage_manager_writes_all_log_types_and_reports_health(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = StorageManager(
                base_path=temp_dir,
                gateway_id="imx93_gateway_1",
                asset_id="pcs_1",
                asset_type="pcs",
            )
            self.assertTrue(manager.initialize())
            self.assertIsInstance(manager.telemetry, TelemetryStore)
            self.assertIsInstance(manager.events, EventStore)
            self.assertIsInstance(manager.errors, ErrorStore)
            self.assertIsInstance(manager.status, StorageStatus)

            self.assertTrue(manager.log_telemetry({"vendor": "njoy", "comm_status": "online"}))
            self.assertTrue(
                manager.log_event(
                    event_type="PCS_TEST_EVENT",
                    command="test",
                    status="success",
                    description="storage manager event test",
                )
            )
            self.assertTrue(
                manager.log_error(
                    error_type="PCS_TEST_ERROR",
                    error_source="test_storage_abstraction.py",
                    description="storage manager error test",
                )
            )

            status = manager.get_status()
            self.assertEqual(status["storage_manager"], "StorageManager")
            self.assertEqual(status["backend"], "csv_storage_logger")
            self.assertEqual(status["logger_status"], "ok")
            self.assertIn("stores", status)

            health = manager.get_health()
            self.assertEqual(health["storage_manager"], "StorageManager")
            self.assertIn(health["status"], {"healthy", "degraded"})
            self.assertIn("disk_free_bytes", health)

            base = Path(temp_dir)
            self.assertTrue((base / "logs" / "pcs_1").exists())
            self.assertTrue((base / "events" / "pcs_1_events.csv").exists())
            self.assertTrue((base / "errors" / "pcs_1_errors.csv").exists())

    def test_log_query_service_exposes_storage_health(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = StorageManager(
                base_path=temp_dir,
                gateway_id="imx93_gateway_1",
                asset_id="bms_1",
                asset_type="bms",
            )
            self.assertTrue(manager.initialize())
            self.assertTrue(manager.log_telemetry("bms_1", {"communication_status": "online", "soc_percent": 50}))

            query = LogQueryService(base_path=temp_dir, asset_id="bms_1")
            health = query.get_storage_health(asset_id="bms_1")

            self.assertIn(health["status"], {"healthy", "degraded"})
            self.assertEqual(health["asset_id"], "bms_1")
            self.assertTrue(health["telemetry_dir_exists"])
            self.assertGreaterEqual(health["telemetry_files_count"], 1)

    def test_storage_manager_exposes_compatibility_aliases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = StorageManager(
                base_path=temp_dir,
                gateway_id="imx93_gateway_1",
                asset_id="chiller_1",
                asset_type="chiller",
            )
            self.assertTrue(manager.initialize())
            self.assertTrue(manager.write_telemetry({"outlet_water_temp": 31.0}))
            self.assertTrue(manager.append_event(event_type="TEST_EVENT", status="success"))
            self.assertTrue(
                manager.write_error(
                    error_type="TEST_ERROR",
                    error_source="test_storage_abstraction.py",
                    description="alias compatibility",
                )
            )
            self.assertEqual(manager.logger_status, "ok")



if __name__ == "__main__":
    unittest.main()
