"""
Asset/profile/protocol configuration checks.

Run from imx93_gateway:
    python3 test_asset_protocol_config.py
"""

import argparse
import json
from pathlib import Path
import tempfile
import unittest

import config as cfg
from core.assets import AssetConfigRegistry
from core.protocols import ProtocolFactory
from core.runtime_config import load_runtime_config
from main import EMSGatewayApplication


ROOT = Path(__file__).resolve().parent


def build_args(**overrides):
    values = dict(
        mock=True,
        config_file=None,
        print_runtime_config=False,
        serial_port=None,
        slave_id=None,
        pc_ip=None,
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
    values.update(overrides)
    return argparse.Namespace(**values)


class AssetProtocolConfigTests(unittest.TestCase):
    def test_asset_list_config_generates_legacy_overrides(self):
        profile = ROOT / "configs" / "lab_pc_simulators.json"
        runtime_config = load_runtime_config(build_args(config_file=str(profile)), cfg, env={})

        self.assertEqual(runtime_config.get("PCS_HOST", ""), "192.168.10.1")
        self.assertEqual(runtime_config.get("PCS_PORT", 0), 1502)
        self.assertEqual(runtime_config.get("BMS_MODBUS_HOST", ""), "192.168.10.1")
        self.assertEqual(runtime_config.get("BMS_MODBUS_PORT", 0), 2502)
        self.assertEqual(runtime_config.get("CHILLER_ENABLED", True), False)
        self.assertTrue(any(source.startswith("asset_list:") for source in runtime_config.get_status()["active_sources"]))

    def test_configured_asset_registry_parses_actual_network_profile(self):
        profile = ROOT / "configs" / "actual_network_assets.json"
        runtime_config = load_runtime_config(build_args(config_file=str(profile)), cfg, env={})
        registry = AssetConfigRegistry.from_runtime_config(runtime_config)

        self.assertEqual(registry.to_status()["asset_count"], 3)
        pcs = registry.find(asset_key="pcs")
        bms = registry.find(asset_type="bms")

        self.assertIsNotNone(pcs)
        self.assertEqual(pcs.vendor, "njoy")
        self.assertEqual(pcs.protocol, "modbus_tcp")
        self.assertEqual(pcs.protocol_descriptor.host, "192.168.1.200")

        self.assertIsNotNone(bms)
        self.assertEqual(bms.vendor, "simulator")
        self.assertEqual(bms.protocol_descriptor.host, "192.168.10.1")

    def test_cli_arguments_still_override_asset_list_profile(self):
        profile = ROOT / "configs" / "lab_pc_simulators.json"
        app = EMSGatewayApplication(
            build_args(
                config_file=str(profile),
                pcs_host="192.168.10.55",
                pcs_port=1602,
                bms_host="192.168.10.56",
                bms_port=2602,
                pc_ip="192.168.10.99",
            )
        )

        self.assertEqual(app.pcs_host, "192.168.10.55")
        self.assertEqual(app.pcs_port, 1602)
        self.assertEqual(app.bms_host, "192.168.10.56")
        self.assertEqual(app.bms_port, 2602)
        self.assertEqual(app.pc_telemetry_ip, "192.168.10.99")

    def test_protocol_factory_marks_current_and_future_protocols(self):
        self.assertTrue(ProtocolFactory.is_supported_by_legacy_service("pcs", "modbus_tcp"))
        self.assertTrue(ProtocolFactory.is_supported_by_legacy_service("bms", "modbus_tcp"))
        self.assertTrue(ProtocolFactory.is_supported_by_legacy_service("chiller", "modbus_rtu"))
        self.assertFalse(ProtocolFactory.is_supported_by_legacy_service("bms", "can"))
        self.assertTrue(ProtocolFactory.is_known_protocol("can"))

    def test_mock_status_exposes_configured_assets(self):
        profile = ROOT / "configs" / "actual_network_assets.json"
        app = EMSGatewayApplication(build_args(config_file=str(profile)))
        try:
            app.start()
            status = app.get_status_packet()
            self.assertIn("configured_assets", status)
            self.assertEqual(status["configured_assets"]["asset_count"], 3)
            self.assertIn("asset_factory_plan", status)
            self.assertEqual(status["asset_factory_plan"]["asset_count"], 3)
        finally:
            app.stop()

    def test_enabled_unsupported_protocol_fails_before_driver_start(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_path = Path(tmpdir) / "bad_protocol.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "assets": [
                            {
                                "asset_key": "bms",
                                "asset_id": "bms_1",
                                "asset_type": "bms",
                                "enabled": True,
                                "vendor": "future_vendor",
                                "protocol": "can",
                                "profile": "future_vendor_can",
                                "connection": {"interface": "can0", "bitrate": 500000},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            app = EMSGatewayApplication(
                build_args(
                    mock=False,
                    config_file=str(profile_path),
                    no_chiller=True,
                    no_pcs=True,
                    no_bms=False,
                )
            )
            with self.assertRaises(RuntimeError) as ctx:
                app.start()
            self.assertIn("protocol 'can'", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
