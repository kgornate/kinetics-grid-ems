"""
Telemetry pipeline compatibility checks.

Run from imx93_gateway:
    python3 test_telemetry_pipeline.py
"""

import argparse
import unittest

from core.telemetry_pipeline import TelemetryPipeline, TelemetryPipelineConfig
from main import EMSGatewayApplication


class FakeAdapter:
    def __init__(self, packet=None, error=None):
        self.packet = packet or {}
        self.error = error
        self.calls = 0

    def get_telemetry(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return dict(self.packet)


class TelemetryPipelineTests(unittest.TestCase):
    def build_pipeline(self, adapters=None, fallbacks=None, mode="real"):
        adapters = adapters or {}
        return TelemetryPipeline(
            config=TelemetryPipelineConfig(
                gateway_id="imx93_gateway_1",
                chiller_asset_id="chiller_1",
                pcs_asset_id="pcs_1",
                bms_asset_id="bms_1",
                pcs_vendor="njoy",
            ),
            get_asset_adapter=lambda key: adapters.get(key),
            get_mode=lambda: mode,
            fallbacks=fallbacks or {},
        )

    def test_legacy_packet_shape_preserves_flutter_top_level_chiller_fields(self):
        pipeline = self.build_pipeline(
            adapters={
                "chiller": FakeAdapter(
                    {
                        "type": "telemetry",
                        "gateway_id": "old_gateway",
                        "asset_id": "chiller_1",
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "status": "ok",
                        "data": {"outlet_water_temp": 38.4},
                    }
                ),
                "pcs": FakeAdapter({"asset_id": "pcs_1", "active_power_kw": 12.5}),
                "bms": FakeAdapter({"asset_id": "bms_1", "soc_percent": 72.0}),
            }
        )

        packet = pipeline.get_legacy_udp_packet()

        self.assertEqual(packet["type"], "telemetry")
        self.assertEqual(packet["gateway_id"], "imx93_gateway_1")
        self.assertEqual(packet["asset_id"], "chiller_1")
        self.assertIn("data", packet)
        self.assertEqual(packet["data"]["outlet_water_temp"], 38.4)
        self.assertEqual(packet["pcs"]["asset_id"], "pcs_1")
        self.assertEqual(packet["bms"]["asset_id"], "bms_1")
        self.assertEqual(packet["assets"]["chiller"]["asset_id"], "chiller_1")

    def test_pipeline_uses_fallback_when_adapter_is_missing(self):
        pipeline = self.build_pipeline(
            adapters={},
            fallbacks={
                "pcs": lambda: {"asset_id": "pcs_1", "active_power_kw": 9.5},
                "bms": lambda: {"asset_id": "bms_1", "soc_percent": 60.0},
            },
        )

        packet = pipeline.get_legacy_udp_packet()

        self.assertIsNone(packet["assets"]["chiller"])
        self.assertEqual(packet["pcs"]["active_power_kw"], 9.5)
        self.assertEqual(packet["bms"]["soc_percent"], 60.0)
        self.assertEqual(packet["status"], "ok")

    def test_adapter_exception_creates_offline_packet_without_throwing(self):
        pipeline = self.build_pipeline(
            adapters={
                "pcs": FakeAdapter(error=RuntimeError("PCS read failed")),
            }
        )

        packet = pipeline.get_legacy_udp_packet()

        self.assertEqual(packet["pcs"]["asset_id"], "pcs_1")
        self.assertEqual(packet["pcs"]["comm_status"], "offline")
        self.assertEqual(packet["pcs"]["vendor"], "njoy")
        self.assertIn("PCS read failed", packet["pcs"]["error"])

    def test_mock_gateway_exposes_telemetry_pipeline_without_network(self):
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
            self.assertIn("telemetry_pipeline", status)
            self.assertEqual(status["telemetry_pipeline"]["pipeline_class"], "TelemetryPipeline")
            self.assertEqual(
                status["telemetry_pipeline"]["legacy_packet_function"],
                "compose_legacy_udp_packet",
            )
        finally:
            app.stop()


if __name__ == "__main__":
    unittest.main()
