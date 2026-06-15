"""Mock chiller gateway service used for local and integration testing."""

from datetime import datetime
from typing import Any, Dict


class MockGatewayService:
    """
    Mock service for testing TCP/UDP communication without Modbus hardware.
    """

    def __init__(
        self,
        gateway_id: str = "imx93_gateway_1",
        asset_id: str = "chiller_1",
    ):
        self.gateway_id = gateway_id
        self.asset_id = asset_id
        self.sequence = 0
        self.running = False

        self.mock_state = {
            "water_pump": "RUNNING",
            "compressor1": "STOPPED",
            "compressor2": "STOPPED",
            "electric_heater": "STOPPED",
            "condensate_fan": "STOPPED",
            "outlet_water_temp": 38.4,
            "return_water_temp": 38.1,
            "outlet_water_pressure": 0.27,
            "return_water_pressure": 0.07,
            "ambient_temp": 37.4,
            "makeup_pump": "ON",
            "fault_code": 0,
            "control_mode": 2,
            "set_temperature": 25.0,
            "communication_status": "mock",
        }

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def start_polling(self) -> None:
        self.running = True
        print("[MOCK SERVICE] Mock polling started")

    def stop_polling(self) -> None:
        self.running = False
        print("[MOCK SERVICE] Mock polling stopped")

    def get_telemetry_packet(self) -> Dict[str, Any]:
        self.sequence += 1

        self.mock_state["outlet_water_temp"] = 38.4 + (self.sequence % 5) * 0.1
        self.mock_state["return_water_temp"] = 38.1 + (self.sequence % 5) * 0.1

        return {
            "type": "telemetry",
            "gateway_id": self.gateway_id,
            "asset_id": self.asset_id,
            "timestamp": self._now(),
            "status": "ok",
            "mode": "mock",
            "data": dict(self.mock_state),
        }

    def execute_command(self, command_packet: Dict[str, Any]) -> Dict[str, Any]:
        request_id = command_packet.get("request_id")
        command = str(command_packet.get("command", "")).strip().upper()
        value = command_packet.get("value")

        def response(message: str, data: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "type": "response",
                "request_id": request_id,
                "timestamp": self._now(),
                "status": "ok",
                "command": command,
                "message": message,
                "data": data,
            }

        def error_response(message: str) -> Dict[str, Any]:
            return {
                "type": "response",
                "request_id": request_id,
                "timestamp": self._now(),
                "status": "error",
                "command": command,
                "message": message,
                "data": {},
            }

        try:
            set_temp = float(self.mock_state.get("set_temperature", 25.0))
            set_temp_raw = int(set_temp * 10)

            water_pump_running = self.mock_state.get("water_pump") == "RUNNING"
            onoff_raw = 1 if water_pump_running else 0
            onoff_status = "ON" if onoff_raw == 1 else "OFF"

            control_mode_raw = int(self.mock_state.get("control_mode", 2))

            read_mode_map = {
                1: "Water pump circulation mode",
                2: "Refrigeration / Cooling mode",
                3: "Heating mode",
                4: "System automatic control mode",
            }

            write_to_readback_mode = {
                0: 4,
                1: 2,
                2: 3,
                3: 1,
            }

            write_mode_name = {
                0: "System automatic control mode",
                1: "Refrigeration / Cooling mode",
                2: "Heating mode",
                3: "Water pump circulation mode",
            }

            if command == "READ_ALL":
                return response(
                    message="Mock telemetry read successfully",
                    data=dict(self.mock_state),
                )

            if command == "READ_TEMP":
                return response(
                    message="Mock set temperature read successfully",
                    data={
                        "register": 205,
                        "raw_value": set_temp_raw,
                        "temperature_celsius": set_temp,
                    },
                )

            if command == "READ_ONOFF":
                return response(
                    message="Mock ON/OFF status read successfully",
                    data={
                        "register": 201,
                        "raw_value": onoff_raw,
                        "status": onoff_status,
                    },
                )

            if command == "READ_MODE":
                return response(
                    message="Mock control mode read successfully",
                    data={
                        "register": 200,
                        "raw_value": control_mode_raw,
                        "mode": read_mode_map.get(control_mode_raw, "Unknown mode"),
                    },
                )

            if command == "READ_SETTINGS":
                return response(
                    message="Mock setting parameters read successfully",
                    data={
                        "raw_registers_200_to_208": [
                            control_mode_raw,
                            onoff_raw,
                            0,
                            0,
                            0,
                            set_temp_raw,
                            0,
                            0,
                            0,
                        ],
                        "control_mode": {
                            "register": 200,
                            "raw_value": control_mode_raw,
                            "mode": read_mode_map.get(control_mode_raw, "Unknown mode"),
                        },
                        "on_off_enable": {
                            "register": 201,
                            "raw_value": onoff_raw,
                            "status": onoff_status,
                        },
                        "reserved_202": 0,
                        "reserved_203": 0,
                        "reserved_204": 0,
                        "set_temperature": {
                            "register": 205,
                            "raw_value": set_temp_raw,
                            "temperature_celsius": set_temp,
                        },
                        "reserved_206": 0,
                        "reserved_207": 0,
                        "reserved_208": 0,
                    },
                )

            if command == "SET_TEMP":
                if value is None:
                    return error_response("SET_TEMP requires value")

                new_temp = float(value)
                new_temp_raw = int(new_temp * 10)
                self.mock_state["set_temperature"] = new_temp

                return response(
                    message="Mock set temperature command executed",
                    data={
                        "status": "ok",
                        "command": "SET_TEMP",
                        "register": 205,
                        "temperature_celsius": new_temp,
                        "written_value": new_temp_raw,
                        "message": "Mock temperature write command successful",
                        "readback": {
                            "register": 205,
                            "raw_value": new_temp_raw,
                            "temperature_celsius": new_temp,
                        },
                        "verified": True,
                    },
                )

            if command == "SET_MODE":
                if value is None:
                    return error_response("SET_MODE requires value")

                write_value = int(value)
                expected_readback = write_to_readback_mode.get(write_value, write_value)
                requested_mode = write_mode_name.get(write_value, "Unknown mode")

                self.mock_state["control_mode"] = expected_readback

                return response(
                    message="Mock set mode command executed",
                    data={
                        "status": "ok",
                        "command": "SET_MODE",
                        "register": 200,
                        "written_value": write_value,
                        "requested_mode": requested_mode,
                        "message": "Mock mode write command successful",
                        "expected_readback_value": expected_readback,
                        "readback": {
                            "register": 200,
                            "raw_value": expected_readback,
                            "mode": read_mode_map.get(expected_readback, "Unknown mode"),
                        },
                        "verified": True,
                    },
                )

            if command == "CHILLER_ON":
                self.mock_state["water_pump"] = "RUNNING"

                return response(
                    message="Mock CHILLER_ON command executed",
                    data={
                        "status": "ok",
                        "command": "CHILLER_ON",
                        "register": 201,
                        "written_value": 1,
                        "message": "Mock chiller ON command successful",
                        "readback": {
                            "register": 201,
                            "raw_value": 1,
                            "status": "ON",
                        },
                        "verified": True,
                    },
                )

            if command == "CHILLER_OFF":
                self.mock_state["water_pump"] = "STOPPED"

                return response(
                    message="Mock CHILLER_OFF command executed",
                    data={
                        "status": "ok",
                        "command": "CHILLER_OFF",
                        "register": 201,
                        "written_value": 0,
                        "message": "Mock chiller OFF command successful",
                        "readback": {
                            "register": 201,
                            "raw_value": 0,
                            "status": "OFF",
                        },
                        "verified": True,
                    },
                )

            return error_response(f"Unsupported mock command: {command}")

        except Exception as error:
            return error_response(str(error))
