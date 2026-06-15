"""
Asset adapter compatibility checks.

Run from imx93_gateway:
    python3 test_asset_adapters.py
"""

import argparse
import unittest

from core.asset_registry import AssetDescriptor
from core.assets import BmsAssetAdapter, ChillerAssetAdapter, PcsAssetAdapter
from main import EMSGatewayApplication


class FakeChillerService:
    def __init__(self):
        self.commands = []

    def get_telemetry_packet(self):
        return {
            "type": "telemetry",
            "gateway_id": "imx93_gateway_1",
            "asset_id": "chiller_1",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "status": "ok",
            "data": {"outlet_water_temp": 38.4},
        }

    def get_latest_state_dict(self):
        return {"outlet_water_temp": 38.4}

    def execute_command(self, command_packet):
        self.commands.append(command_packet)
        return {
            "type": "response",
            "request_id": command_packet.get("request_id"),
            "status": "ok",
            "command": command_packet.get("command"),
            "message": "chiller ok",
            "data": {"echo": command_packet},
        }


class FakePcsService:
    def __init__(self):
        self.active_power_calls = []
        self.reactive_power_calls = []

    def get_latest_state(self):
        return {"asset_id": "pcs_1", "active_power_kw": 12.5}

    def power_on(self, source="gateway"):
        return {"status": "success", "description": "PCS power on", "source": source}

    def power_off(self, source="gateway"):
        return {"status": "success", "description": "PCS power off", "source": source}

    def standby(self, source="gateway"):
        return {"status": "success", "description": "PCS standby", "source": source}

    def set_active_power_kw(self, power_kw, verify=True, source="gateway"):
        self.active_power_calls.append((power_kw, verify, source))
        return {"status": "success", "description": "PCS active power set", "value": power_kw}

    def set_reactive_power_kvar(self, reactive_power_kvar, verify=True, source="gateway"):
        self.reactive_power_calls.append((reactive_power_kvar, verify, source))
        return {"status": "success", "description": "PCS reactive power set", "value": reactive_power_kvar}

    def reset_fault(self, source="gateway"):
        return {"status": "success", "description": "PCS fault reset", "source": source}

    def heartbeat(self, value=None, verify=True, source="gateway"):
        return {"status": "success", "description": "PCS heartbeat", "value": value, "source": source}


class FakeBmsService:
    def __init__(self):
        self.commands = []

    def get_telemetry_payload(self):
        return {"asset_id": "bms_1", "soc_percent": 72.0}

    def get_latest_state_dict(self):
        return {"asset_id": "bms_1", "soc_percent": 72.0}

    def execute_command(self, command):
        self.commands.append(command)
        return {"status": "success", "message": "BMS command executed", "command": command}


class AssetAdapterTests(unittest.TestCase):
    def descriptor(self, key, asset_id, asset_type):
        return AssetDescriptor(
            asset_key=key,
            asset_id=asset_id,
            asset_type=asset_type,
            service=None,
        )

    def test_chiller_adapter_delegates_telemetry_and_command_shape(self):
        service = FakeChillerService()
        adapter = ChillerAssetAdapter(
            descriptor=self.descriptor("chiller", "chiller_1", "chiller"),
            service=service,
            mode="real",
        )

        telemetry = adapter.get_telemetry()
        self.assertEqual(telemetry["asset_id"], "chiller_1")
        self.assertEqual(telemetry["data"]["outlet_water_temp"], 38.4)

        response = adapter.execute_command({"request_id": "CH_1", "command": "READ_ALL"})
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["request_id"], "CH_1")
        self.assertEqual(service.commands[0]["command"], "READ_ALL")

    def test_pcs_adapter_preserves_read_and_write_response_shape(self):
        service = FakePcsService()
        adapter = PcsAssetAdapter(
            descriptor=self.descriptor("pcs", "pcs_1", "pcs"),
            service=service,
            vendor="njoy",
        )

        read_response = adapter.execute_command({"request_id": "PCS_R", "command": "PCS_READ"})
        self.assertEqual(read_response["type"], "response")
        self.assertEqual(read_response["status"], "ok")
        self.assertEqual(read_response["data"]["active_power_kw"], 12.5)

        write_response = adapter.execute_command(
            {"request_id": "PCS_W", "command": "PCS_SET_ACTIVE_POWER", "value": 20.0}
        )
        self.assertEqual(write_response["status"], "ok")
        self.assertEqual(write_response["message"], "PCS active power set")
        self.assertEqual(service.active_power_calls[0][0], 20.0)

    def test_bms_adapter_preserves_command_string_execution(self):
        service = FakeBmsService()
        adapter = BmsAssetAdapter(
            descriptor=self.descriptor("bms", "bms_1", "bms"),
            service=service,
        )

        telemetry = adapter.get_telemetry()
        self.assertEqual(telemetry["soc_percent"], 72.0)

        response = adapter.execute_command({"request_id": "BMS_R", "command": "READ_BMS_ALL"})
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["message"], "BMS command executed")
        self.assertEqual(service.commands, ["READ_BMS_ALL"])

    def test_mock_gateway_uses_adapter_without_network(self):
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
            self.assertIn("asset_adapters", status)
            self.assertIn("chiller", status["asset_adapters"])
            self.assertEqual(
                status["asset_adapters"]["chiller"]["adapter_class"],
                "ChillerAssetAdapter",
            )

            response = app.execute_command({"request_id": "MOCK_READ", "command": "READ_ALL"})
            self.assertEqual(response["status"], "ok")
        finally:
            app.stop()


if __name__ == "__main__":
    unittest.main()
