"""
Runtime configuration compatibility checks.

Run from imx93_gateway:
    python3 test_runtime_config.py
"""

import argparse
import json
from pathlib import Path
import tempfile
import unittest

import config as cfg
from core.runtime_config import load_runtime_config
from main import EMSGatewayApplication


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


class RuntimeConfigTests(unittest.TestCase):
    def test_without_config_file_uses_config_py_defaults(self):
        runtime_config = load_runtime_config(build_args(), cfg, env={})

        self.assertEqual(runtime_config.get("PCS_HOST", "missing"), cfg.PCS_HOST)
        self.assertEqual(runtime_config.get("WEB_API_PORT", 0), cfg.WEB_API_PORT)
        self.assertIn("config.py", runtime_config.get_status()["active_sources"])
        self.assertIsNone(runtime_config.get_status()["config_file"])

    def test_json_config_file_overrides_config_py(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_path = Path(tmpdir) / "field_profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "PCS_HOST": "192.168.1.200",
                        "PCS_PORT": 502,
                        "WEB_API_PORT": 8100,
                        "BMS_MODBUS_HOST": "192.168.10.1",
                    }
                ),
                encoding="utf-8",
            )

            runtime_config = load_runtime_config(build_args(config_file=str(profile_path)), cfg, env={})

        self.assertEqual(runtime_config.get("PCS_HOST", ""), "192.168.1.200")
        self.assertEqual(runtime_config.get("WEB_API_PORT", 0), 8100)
        self.assertEqual(runtime_config.get("BMS_MODBUS_HOST", ""), "192.168.10.1")
        self.assertTrue(any(source.startswith("config_file:") for source in runtime_config.get_status()["active_sources"]))

    def test_nested_json_config_profile_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_path = Path(tmpdir) / "nested_profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "pcs": {"host": "192.168.1.200", "unit_id": 1},
                        "bms": {"host": "192.168.10.1", "port": 1502},
                        "network": {"pc_telemetry_ip": "192.168.10.1"},
                        "web_api": {"port": 8000},
                    }
                ),
                encoding="utf-8",
            )

            runtime_config = load_runtime_config(build_args(config_file=str(profile_path)), cfg, env={})

        self.assertEqual(runtime_config.get("PCS_HOST", ""), "192.168.1.200")
        self.assertEqual(runtime_config.get("PCS_UNIT_ID", 0), 1)
        self.assertEqual(runtime_config.get("BMS_MODBUS_HOST", ""), "192.168.10.1")
        self.assertEqual(runtime_config.get("BMS_MODBUS_PORT", 0), 1502)
        self.assertEqual(runtime_config.get("PC_TELEMETRY_IP", ""), "192.168.10.1")
        self.assertEqual(runtime_config.get("WEB_API_PORT", 0), 8000)

    def test_environment_overrides_config_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_path = Path(tmpdir) / "profile.json"
            profile_path.write_text(json.dumps({"PCS_HOST": "192.168.1.200"}), encoding="utf-8")
            runtime_config = load_runtime_config(
                build_args(config_file=str(profile_path)),
                cfg,
                env={"EMS_PCS_HOST": "192.168.1.210", "EMS_WEB_API_ENABLE_AUTH": "true"},
            )

        self.assertEqual(runtime_config.get("PCS_HOST", ""), "192.168.1.210")
        self.assertEqual(runtime_config.get("WEB_API_ENABLE_AUTH", False), True)
        self.assertIn("environment", runtime_config.get_status()["active_sources"])

    def test_existing_cli_arguments_still_have_highest_priority_in_application(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_path = Path(tmpdir) / "profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "PCS_HOST": "192.168.1.200",
                        "BMS_MODBUS_HOST": "192.168.10.1",
                        "PC_TELEMETRY_IP": "192.168.10.1",
                        "WEB_API_PORT": 8000,
                    }
                ),
                encoding="utf-8",
            )

            app = EMSGatewayApplication(
                build_args(
                    config_file=str(profile_path),
                    pcs_host="192.168.1.250",
                    bms_host="192.168.10.55",
                    pc_ip="127.0.0.1",
                    web_api_port=8088,
                )
            )

        self.assertEqual(app.pcs_host, "192.168.1.250")
        self.assertEqual(app.bms_host, "192.168.10.55")
        self.assertEqual(app.pc_telemetry_ip, "127.0.0.1")
        self.assertEqual(app.web_api_port, 8088)

    def test_mock_gateway_status_exposes_runtime_config_without_network(self):
        app = EMSGatewayApplication(build_args())
        try:
            app.start()
            status = app.get_status_packet()
            self.assertIn("runtime_config", status)
            self.assertEqual(status["runtime_config"]["config_class"], "RuntimeConfig")
            self.assertIn("config.py", status["runtime_config"]["active_sources"])
        finally:
            app.stop()


if __name__ == "__main__":
    unittest.main()
