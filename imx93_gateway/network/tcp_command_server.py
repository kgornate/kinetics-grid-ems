"""
TCP Command Server for i.MX93 EMS Gateway.

Role of this file:
- Runs a TCP server on i.MX93.
- Receives control/read commands from PC Dashboard.
- Passes commands to the main EMS command handler.
- Sends ACK/NACK response back to PC.

Direction:
    PC Dashboard  --->  i.MX93 Gateway

Protocol:
- TCP
- JSON message format
- Newline-delimited JSON

Examples:
    {"request_id":"REQ_001","command":"SET_TEMP","value":25.0}
    {"request_id":"REQ_101","command":"PCS_SET_ACTIVE_POWER","value":20}
    {"request_id":"REQ_201","command":"READ_BMS_ALL"}
    {"request_id":"REQ_202","command":"START_BMS_PRECHARGE"}
    {"request_id":"REQ_203","command":"BMS_FAN_ON"}

Important:
TCP is stream-based, not packet-based.
So every message must end with newline: \n
This class is asset-agnostic. It does not know Chiller/PCS/BMS details;
main.py performs the actual command routing.
"""

import json
import socket
import threading
from datetime import datetime
from typing import Callable, Dict, Any, Optional, Tuple


class TCPCommandServer:
    def __init__(
        self,
        host: str,
        port: int,
        command_handler: Callable[[Dict[str, Any]], Dict[str, Any]],
        server_name: str = "ems_tcp_command_server",
        recv_buffer_size: int = 4096,
    ):
        self.host = host
        self.port = int(port)
        self.command_handler = command_handler
        self.server_name = server_name
        self.recv_buffer_size = int(recv_buffer_size)

        self.sock: Optional[socket.socket] = None
        self._running = False
        self._server_thread: Optional[threading.Thread] = None

        self.total_connections = 0
        self.total_commands = 0
        self.last_client: Optional[str] = None
        self.last_command_time: Optional[str] = None
        self.last_error: Optional[str] = None

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _json_dumps(data: Dict[str, Any]) -> str:
        return json.dumps(data, default=str) + "\n"

    def _create_socket(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(5)

    def _close_socket(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def start(self) -> None:
        if self._running:
            print("[TCP] Command server already running")
            return
        self._create_socket()
        self._running = True
        self._server_thread = threading.Thread(
            target=self._server_loop,
            name="TCPCommandServerThread",
            daemon=True,
        )
        self._server_thread.start()
        print(f"[TCP] Command server started | listening={self.host}:{self.port}")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._close_socket()
        if self._server_thread is not None:
            self._server_thread.join(timeout=2)
        print("[TCP] Command server stopped")

    def is_running(self) -> bool:
        return self._running

    def _server_loop(self) -> None:
        while self._running:
            try:
                if self.sock is None:
                    break
                client_socket, client_address = self.sock.accept()
                self.total_connections += 1
                self.last_client = f"{client_address[0]}:{client_address[1]}"
                print(f"[TCP] Client connected: {self.last_client}")
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_address),
                    daemon=True,
                )
                client_thread.start()
            except OSError:
                break
            except Exception as e:
                self.last_error = str(e)
                print(f"[TCP] Server loop error: {e}")

    def _handle_client(self, client_socket: socket.socket, client_address: Tuple[str, int]) -> None:
        client_id = f"{client_address[0]}:{client_address[1]}"
        buffer = ""
        try:
            with client_socket:
                client_socket.settimeout(None)
                while self._running:
                    data = client_socket.recv(self.recv_buffer_size)
                    if not data:
                        print(f"[TCP] Client disconnected: {client_id}")
                        break
                    buffer += data.decode("utf-8", errors="replace")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        response = self._process_raw_message(line, client_id)
                        client_socket.sendall(self._json_dumps(response).encode("utf-8"))
        except ConnectionResetError:
            print(f"[TCP] Client reset connection: {client_id}")
        except Exception as e:
            self.last_error = str(e)
            print(f"[TCP] Client handler error from {client_id}: {e}")

    def _process_raw_message(self, raw_message: str, client_id: str) -> Dict[str, Any]:
        self.total_commands += 1
        self.last_command_time = self._now()
        print(f"[TCP] Received from {client_id}: {raw_message}")
        try:
            command_packet = self._parse_command(raw_message)
            if "client" not in command_packet:
                command_packet["client"] = client_id
            response = self.command_handler(command_packet)
            if not isinstance(response, dict):
                raise ValueError("Command handler must return dictionary response")
            return response
        except Exception as e:
            self.last_error = str(e)
            return {
                "type": "response",
                "request_id": None,
                "timestamp": self._now(),
                "status": "error",
                "command": None,
                "message": str(e),
                "data": {},
            }

    def _parse_command(self, raw_message: str) -> Dict[str, Any]:
        raw_message = raw_message.strip()
        try:
            parsed = json.loads(raw_message)
            if not isinstance(parsed, dict):
                raise ValueError("JSON command must be an object/dictionary")
            return parsed
        except json.JSONDecodeError:
            pass

        parts = raw_message.split()
        if not parts:
            raise ValueError("Empty command")

        command = parts[0].strip().upper()
        packet: Dict[str, Any] = {"request_id": None, "command": command}

        commands_requiring_value = {
            "SET_TEMP",
            "SET_MODE",
            "PCS_SET_ACTIVE_POWER",
            "PCS_SET_REACTIVE_POWER",
            "PCS_HEARTBEAT",
        }

        if command in commands_requiring_value:
            if len(parts) < 2:
                raise ValueError(f"{command} requires value")
            value = parts[1]
            if command in ["SET_TEMP", "PCS_SET_ACTIVE_POWER", "PCS_SET_REACTIVE_POWER"]:
                packet["value"] = float(value)
            elif command in ["SET_MODE", "PCS_HEARTBEAT"]:
                packet["value"] = int(float(value))
            else:
                packet["value"] = value

        return packet

    def get_status(self) -> Dict[str, Any]:
        return {
            "server_name": self.server_name,
            "running": self._running,
            "host": self.host,
            "port": self.port,
            "total_connections": self.total_connections,
            "total_commands": self.total_commands,
            "last_client": self.last_client,
            "last_command_time": self.last_command_time,
            "last_error": self.last_error,
        }


def _mock_command_handler(command_packet: Dict[str, Any]) -> Dict[str, Any]:
    command = str(command_packet.get("command", "")).upper()
    value = command_packet.get("value")
    request_id = command_packet.get("request_id")
    return {
        "type": "response",
        "request_id": request_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": "ok",
        "command": command,
        "message": "Mock command received successfully",
        "data": {
            "received_command": command,
            "received_value": value,
            "note": "This is mock TCP test. No Modbus command executed.",
        },
    }


if __name__ == "__main__":
    HOST = "0.0.0.0"
    PORT = 6000
    server = TCPCommandServer(host=HOST, port=PORT, command_handler=_mock_command_handler)
    try:
        server.start()
        print("[TCP TEST] Press Ctrl+C to stop")
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        print("\n[TCP TEST] Stopping...")
    finally:
        server.stop()
