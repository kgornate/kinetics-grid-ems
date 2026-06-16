"""Health monitoring and diagnostics checks."""

import unittest

from core.health import HealthMonitor


class HealthMonitoringTests(unittest.TestCase):
    def build_monitor(self, storage_status="healthy"):
        status = {
            "gateway_id": "imx93_gateway_1",
            "mode": "real",
            "chiller": {"enabled": False, "running": False, "asset_id": "chiller_1", "protocol": "modbus_rtu"},
            "pcs": {
                "enabled": True,
                "running": True,
                "asset_id": "pcs_1",
                "vendor": "njoy",
                "protocol": "modbus_tcp",
                "host": "192.168.1.200",
                "port": 502,
                "unit_id": 1,
                "state": {"last_success_ts": "2026-06-12T10:00:00+00:00"},
            },
            "bms": {
                "enabled": True,
                "running": True,
                "asset_id": "bms_1",
                "vendor": "simulator",
                "protocol": "modbus_tcp",
                "host": "192.168.10.1",
                "port": 502,
                "unit_id": 1,
            },
            "web_api": {"enabled": True, "running": True, "port": 8000},
            "log_http": {"enabled": True, "host": "0.0.0.0", "port": 7000},
            "udp_streamer": {"running": True},
            "tcp_server": {"running": True},
        }
        telemetry = {
            "timestamp": "2026-06-12T10:00:01+00:00",
            "asset_id": "chiller_1",
            "data": {"communication_status": "ok"},
            "pcs": {"asset_id": "pcs_1", "comm_status": "online", "active_power_kw": 12.0},
            "bms": {"asset_id": "bms_1", "comm_status": "error", "error": "Connection refused"},
            "assets": {
                "pcs": {"asset_id": "pcs_1", "comm_status": "online"},
                "bms": {"asset_id": "bms_1", "comm_status": "error", "error": "Connection refused"},
            },
        }
        return HealthMonitor(
            status_packet=status,
            telemetry_packet=telemetry,
            storage_health_provider=lambda asset_id: {"status": storage_status, "asset_id": asset_id},
        )

    def test_asset_health_classifies_disabled_healthy_and_degraded(self):
        monitor = self.build_monitor()

        chiller = monitor.build_asset_health("chiller_1")
        pcs = monitor.build_asset_health("pcs_1")
        bms = monitor.build_asset_health("bms_1")

        self.assertEqual(chiller["status"], "disabled")
        self.assertEqual(pcs["status"], "healthy")
        self.assertEqual(bms["status"], "degraded")
        self.assertIn("192.168.10.1", bms["recommended_action"])

    def test_overall_health_summary_and_diagnostics(self):
        monitor = self.build_monitor()
        overall = monitor.build_overall_health()
        diagnostics = monitor.build_diagnostics("bms_1")

        self.assertEqual(overall["status"], "degraded")
        self.assertEqual(overall["summary"]["healthy"], 1)
        self.assertEqual(overall["summary"]["degraded"], 1)
        self.assertEqual(overall["summary"]["disabled"], 1)
        self.assertEqual(diagnostics["diagnostics"]["severity"], "warning")
        self.assertIn("recommended_action", diagnostics["diagnostics"])

    def test_storage_degraded_changes_asset_to_degraded(self):
        monitor = self.build_monitor(storage_status="degraded")
        pcs = monitor.build_asset_health("pcs_1")
        self.assertEqual(pcs["status"], "degraded")
        self.assertIn("storage", pcs["reason"].lower())


if __name__ == "__main__":
    unittest.main()
