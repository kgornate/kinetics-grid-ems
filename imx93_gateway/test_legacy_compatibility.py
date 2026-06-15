"""
Legacy compatibility checks.

Run from imx93_gateway:
    python3 test_legacy_compatibility.py
"""

import argparse
import unittest

from core.command_router import is_bms_command, is_pcs_command
from core.telemetry_composer import compose_legacy_udp_packet
from main import EMSGatewayApplication


class LegacyCompatibilityTests(unittest.TestCase):
    def test_chiller_packet_stays_top_level_for_flutter(self):
        chiller = {
            "type": "telemetry",
            "gateway_id": "old_gateway",
            "asset_id": "chiller_1",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "status": "ok",
            "data": {"outlet_water_temp": 38.4},
        }
        pcs = {"asset_id": "pcs_1", "active_power_kw": 12.3}
        bms = {"asset_id": "bms_1", "soc_percent": 72.0}

        packet = compose_legacy_udp_packet(
            gateway_id="imx93_gateway_1",
            mode="real",
            chiller_asset_id="chiller_1",
            pcs_asset_id="pcs_1",
            bms_asset_id="bms_1",
            chiller_packet=chiller,
            pcs_packet=pcs,
            bms_packet=bms,
            timestamp="2026-01-01T00:00:01+00:00",
        )

        self.assertEqual(packet["asset_id"], "chiller_1")
        self.assertEqual(packet["data"]["outlet_water_temp"], 38.4)
        self.assertEqual(packet["pcs"], pcs)
        self.assertEqual(packet["bms"], bms)
        self.assertEqual(packet["assets"]["chiller"], chiller)

    def test_pcs_bms_only_packet_remains_combined(self):
        packet = compose_legacy_udp_packet(
            gateway_id="imx93_gateway_1",
            mode="real",
            chiller_asset_id="chiller_1",
            pcs_asset_id="pcs_1",
            bms_asset_id="bms_1",
            chiller_packet=None,
            pcs_packet={"asset_id": "pcs_1"},
            bms_packet={"asset_id": "bms_1"},
            timestamp="2026-01-01T00:00:01+00:00",
        )

        self.assertEqual(packet["asset_id"], "pcs_1")
        self.assertEqual(packet["status"], "ok")
        self.assertIsNone(packet["assets"]["chiller"])
        self.assertEqual(packet["assets"]["pcs"]["asset_id"], "pcs_1")

    def test_command_classification_keeps_existing_routes(self):
        self.assertTrue(is_pcs_command({"command": "PCS_SET_ACTIVE_POWER"}, "pcs_1"))
        self.assertTrue(is_pcs_command({"command": "READ_PCS"}, "pcs_1"))
        self.assertTrue(is_pcs_command({"command": "ANY", "asset_type": "pcs"}, "pcs_1"))
        self.assertTrue(is_bms_command({"command": "READ_BMS_ALARMS"}, "bms_1"))
        self.assertTrue(is_bms_command({"command": "BMS_READ_ALL"}, "bms_1"))
        self.assertTrue(is_bms_command({"command": "ANY", "asset_id": "bms_1"}, "bms_1"))

    def test_mock_gateway_registers_chiller_without_network(self):
        args = argparse.Namespace(
            mock=True,
            serial_port=None,
            slave_id=None,
            pc_ip="127.0.0.1",
            udp_port=None,
            tcp_port=None,
            poll_interval=None,
            udp_interval=None,
            pcs_host=None,
            pcs_port=None,
            pcs_unit=None,
            pcs_vendor=None,
            pcs_poll_interval=None,
            bms_host=None,
            bms_port=None,
            bms_unit=None,
            bms_poll_interval=None,
            no_chiller=False,
            no_pcs=True,
            no_bms=True,
            no_udp=True,
            no_tcp=True,
            no_log_http=True,
            log_http_port=None,
            no_web_api=True,
            web_api_port=None,
        )
        app = EMSGatewayApplication(args)
        try:
            app.start()
            telemetry = app.get_udp_telemetry_packet()
            status = app.get_status_packet()
            self.assertEqual(telemetry["asset_id"], "chiller_1")
            self.assertIn("asset_registry", status)
            self.assertTrue(status["asset_registry"]["asset_count"] >= 1)
        finally:
            app.stop()


if __name__ == "__main__":
    unittest.main()
