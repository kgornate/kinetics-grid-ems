"""Operator telemetry view checks.

Run from imx93_gateway:
    python3 test_operator_telemetry_view.py
"""

import unittest

from core.operator_telemetry_view import make_operator_response, should_hide_operator_key


class OperatorTelemetryViewTests(unittest.TestCase):
    def test_operator_view_removes_storage_logger_and_raw_fields(self):
        packet = {
            "type": "telemetry",
            "gateway_id": "imx93_gateway_1",
            "asset_id": "chiller_1",
            "timestamp": "2026-06-12T10:50:14+00:00",
            "storage_logger": {"base_path": "/home/root/ems_logs_test"},
            "data": {
                "outlet_water_temp": 29.4,
                "fault_code": 16878,
                "fault_active": True,
                "fault_description": "Fault text",
                "settings_registers_200_to_208": [3, 0, 0, 0],
                "control_mode_raw": 3,
                "fault_binary": "0100000111101110",
                "fault_active_bits": [1, 2, 3],
                "communication_status": "error",
            },
        }

        filtered = make_operator_response(packet)

        self.assertEqual(filtered["view"], "operator")
        self.assertNotIn("storage_logger", filtered)
        self.assertIn("data", filtered)
        self.assertEqual(filtered["data"]["outlet_water_temp"], 29.4)
        self.assertEqual(filtered["data"]["fault_code"], 16878)
        self.assertTrue(filtered["data"]["fault_active"])
        self.assertIn("fault_description", filtered["data"])
        self.assertIn("communication_status", filtered["data"])
        self.assertNotIn("settings_registers_200_to_208", filtered["data"])
        self.assertNotIn("control_mode_raw", filtered["data"])
        self.assertNotIn("fault_binary", filtered["data"])
        self.assertNotIn("fault_active_bits", filtered["data"])

    def test_hide_key_rules_are_conservative(self):
        self.assertTrue(should_hide_operator_key("raw_telemetry_registers"))
        self.assertTrue(should_hide_operator_key("control_mode_raw"))
        self.assertTrue(should_hide_operator_key("settings_registers_200_to_208"))
        self.assertFalse(should_hide_operator_key("fault_code"))
        self.assertFalse(should_hide_operator_key("fault_active"))
        self.assertFalse(should_hide_operator_key("control_mode"))


if __name__ == "__main__":
    unittest.main()
