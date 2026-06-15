"""
Command dispatcher compatibility checks.

Run from imx93_gateway:
    python3 test_command_dispatcher.py
"""

import argparse
import unittest

from core.command_dispatcher import CommandDispatcher
from main import EMSGatewayApplication


class DummyAdapter:
    def __init__(self, route_name):
        self.route_name = route_name
        self.commands = []

    def execute_command(self, command_packet):
        self.commands.append(command_packet)
        return {
            "type": "response",
            "request_id": command_packet.get("request_id"),
            "status": "ok",
            "command": command_packet.get("command"),
            "message": f"{self.route_name} adapter executed",
            "data": {"route": self.route_name},
        }


class CommandDispatcherTests(unittest.TestCase):
    def build_dispatcher(self, adapters=None, bms_commands=None):
        adapters = adapters or {}
        bms_commands = bms_commands or set()
        return CommandDispatcher(
            gateway_id="imx93_gateway_1",
            get_asset_adapter=lambda key: adapters.get(key),
            get_status_packet=lambda: {"gateway_id": "imx93_gateway_1", "status": "ok"},
            get_telemetry_packet=lambda: {"type": "telemetry", "assets": {}},
            bms_asset_id="bms_1",
            pcs_asset_id="pcs_1",
            configured_bms_commands_provider=lambda: bms_commands,
        )

    def test_gateway_status_and_combined_telemetry_keep_response_shape(self):
        dispatcher = self.build_dispatcher()

        status_response = dispatcher.dispatch({"request_id": "S1", "command": "STATUS"})
        self.assertEqual(status_response["type"], "response")
        self.assertEqual(status_response["status"], "ok")
        self.assertEqual(status_response["message"], "Gateway status read successfully")
        self.assertEqual(status_response["data"]["gateway_id"], "imx93_gateway_1")

        telemetry_response = dispatcher.dispatch({"request_id": "T1", "command": "READ_ALL_ASSETS"})
        self.assertEqual(telemetry_response["status"], "ok")
        self.assertEqual(telemetry_response["message"], "Combined telemetry read successfully")
        self.assertEqual(telemetry_response["data"]["type"], "telemetry")

    def test_routes_pcs_bms_and_chiller_commands_to_adapters(self):
        adapters = {
            "pcs": DummyAdapter("pcs"),
            "bms": DummyAdapter("bms"),
            "chiller": DummyAdapter("chiller"),
        }
        dispatcher = self.build_dispatcher(adapters=adapters)

        pcs_response = dispatcher.dispatch({"request_id": "P1", "command": "PCS_READ"})
        self.assertEqual(pcs_response["data"]["route"], "pcs")
        self.assertEqual(adapters["pcs"].commands[0]["command"], "PCS_READ")

        bms_response = dispatcher.dispatch({"request_id": "B1", "command": "READ_BMS_ALL"})
        self.assertEqual(bms_response["data"]["route"], "bms")
        self.assertEqual(adapters["bms"].commands[0]["command"], "READ_BMS_ALL")

        chiller_response = dispatcher.dispatch({"request_id": "C1", "command": "READ_ALL"})
        self.assertEqual(chiller_response["data"]["route"], "chiller")
        self.assertEqual(adapters["chiller"].commands[0]["command"], "READ_ALL")

    def test_asset_id_and_configured_bms_command_routes_are_preserved(self):
        adapters = {
            "pcs": DummyAdapter("pcs"),
            "bms": DummyAdapter("bms"),
        }
        dispatcher = self.build_dispatcher(adapters=adapters, bms_commands={"CUSTOM_BMS_CMD"})

        pcs_response = dispatcher.dispatch(
            {"request_id": "P2", "command": "ANY_COMMAND", "asset_id": "pcs_1"}
        )
        self.assertEqual(pcs_response["data"]["route"], "pcs")

        bms_response = dispatcher.dispatch({"request_id": "B2", "command": "CUSTOM_BMS_CMD"})
        self.assertEqual(bms_response["data"]["route"], "bms")

    def test_missing_adapter_error_messages_match_previous_behavior(self):
        dispatcher = self.build_dispatcher()

        pcs_response = dispatcher.dispatch({"request_id": "P3", "command": "PCS_READ"})
        self.assertEqual(pcs_response["status"], "error")
        self.assertEqual(pcs_response["message"], "PCS service is not running")

        bms_response = dispatcher.dispatch({"request_id": "B3", "command": "READ_BMS_ALL"})
        self.assertEqual(bms_response["status"], "error")
        self.assertEqual(bms_response["message"], "BMS service is not running")

    def test_mock_gateway_uses_command_dispatcher_without_network(self):
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
            status = app.get_status_packet()
            self.assertIn("command_dispatcher", status)
            self.assertEqual(status["command_dispatcher"]["dispatcher_class"], "CommandDispatcher")

            read_response = app.execute_command({"request_id": "MOCK_READ", "command": "READ_ALL"})
            self.assertEqual(read_response["status"], "ok")
            self.assertEqual(read_response["request_id"], "MOCK_READ")

            gateway_response = app.execute_command({"request_id": "MOCK_STATUS", "command": "STATUS"})
            self.assertEqual(gateway_response["status"], "ok")
            self.assertIn("command_dispatcher", gateway_response["data"])
        finally:
            app.stop()


if __name__ == "__main__":
    unittest.main()
