"""Dynamic asset runtime catalog checks."""

import unittest

from core.assets import RuntimeAssetCatalog
from core.health import HealthMonitor


class DynamicAssetRuntimeTests(unittest.TestCase):
    def build_packets(self):
        status_packet = {
            "gateway_id": "imx93_gateway_1",
            "configured_assets": {
                "assets": [
                    {
                        "asset_key": "pcs",
                        "asset_id": "pcs_1",
                        "asset_type": "pcs",
                        "enabled": True,
                        "vendor": "njoy",
                        "protocol": "modbus_tcp",
                        "profile": "njoy_125kw",
                        "connection": {"host": "192.168.1.200", "port": 502, "unit_id": 1},
                        "compatibility": {"legacy_service_supported": True},
                    },
                    {
                        "asset_key": "meter_1",
                        "asset_id": "meter_1",
                        "asset_type": "energy_meter",
                        "enabled": False,
                        "vendor": "kew",
                        "protocol": "modbus_rtu",
                        "profile": "kew_meter_modbus_rtu_v1",
                        "connection": {"serial_port": "/dev/ttyUSB2", "slave_id": 1},
                        "compatibility": {"legacy_service_supported": False},
                    },
                ]
            },
            "pcs": {
                "enabled": True,
                "running": True,
                "asset_id": "pcs_1",
                "vendor": "njoy",
                "protocol": "modbus_tcp",
                "profile": "njoy_125kw",
                "host": "192.168.1.200",
                "port": 502,
                "unit_id": 1,
            },
            "bms": {"enabled": False, "running": False, "asset_id": "bms_1"},
            "chiller": {"enabled": False, "running": False, "asset_id": "chiller_1"},
        }
        telemetry_packet = {
            "timestamp": "2026-06-12T12:00:00+00:00",
            "assets": {"pcs": {"asset_id": "pcs_1", "comm_status": "online"}},
            "pcs": {"asset_id": "pcs_1", "comm_status": "online"},
        }
        return status_packet, telemetry_packet

    def test_runtime_catalog_merges_configured_and_active_assets(self):
        status_packet, telemetry_packet = self.build_packets()
        catalog = RuntimeAssetCatalog.from_packets(status_packet=status_packet, telemetry_packet=telemetry_packet)
        response = catalog.to_response(gateway_id="imx93_gateway_1", timestamp="now")

        self.assertGreaterEqual(response["assets_count"], 4)
        self.assertIsNotNone(catalog.find("pcs_1"))
        self.assertIsNotNone(catalog.find("meter_1"))
        self.assertEqual(catalog.find("pcs_1").runtime_mode, "active_service")
        self.assertEqual(catalog.find("meter_1").runtime_mode, "disabled")
        self.assertTrue(catalog.find("pcs_1").online)

    def test_health_monitor_uses_runtime_catalog_assets(self):
        status_packet, telemetry_packet = self.build_packets()
        health = HealthMonitor(status_packet=status_packet, telemetry_packet=telemetry_packet).build_assets_health()

        self.assertIn("pcs_1", health["assets"])
        self.assertIn("meter_1", health["assets"])
        self.assertEqual(health["assets"]["pcs_1"]["status"], "healthy")
        self.assertEqual(health["assets"]["meter_1"]["status"], "disabled")


if __name__ == "__main__":
    unittest.main()
