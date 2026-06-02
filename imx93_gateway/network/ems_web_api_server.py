"""
EMS Web API Server for i.MX93 EMS Gateway.

Purpose:
- Expose browser/backend friendly REST APIs for the EMS web dashboard.
- Expose gateway status, asset discovery, latest telemetry, command APIs,
  telemetry keys, optional timeseries-from-logs, and SSE live telemetry stream.
- Reuse existing gateway callbacks from main.py instead of directly touching
  Modbus drivers/services.
- Use only Python standard library. No Flask/FastAPI dependency is required.

Recommended use:
    http://<imx93_wifi_ip>:8000/api/gateway/health
    http://<imx93_wifi_ip>:8000/api/telemetry/latest
    http://<imx93_wifi_ip>:8000/api/stream/telemetry
"""

import json
import time
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse


JsonDict = Dict[str, Any]


class EMSWebAPIServer:
    """
    Lightweight web API server for the EMS gateway.

    This server deliberately does not perform Modbus reads directly. It reads
    latest data through the callbacks provided by main.py:
        - get_status_callback()
        - get_telemetry_callback()
        - execute_command_callback(command_packet)
    """

    def __init__(
        self,
        host: str,
        port: int,
        get_status_callback: Callable[[], JsonDict],
        get_telemetry_callback: Callable[[], JsonDict],
        execute_command_callback: Callable[[JsonDict], JsonDict],
        log_query_service: Optional[Any] = None,
        stream_interval_sec: float = 1.0,
        cors_allow_origin: str = "*",
        enable_auth: bool = False,
        api_key: str = "change-this-key",
        server_name: str = "ems_web_api_server",
    ):
        self.host = host
        self.port = int(port)
        self.get_status_callback = get_status_callback
        self.get_telemetry_callback = get_telemetry_callback
        self.execute_command_callback = execute_command_callback
        self.log_query_service = log_query_service
        self.stream_interval_sec = float(stream_interval_sec)
        self.cors_allow_origin = cors_allow_origin or "*"
        self.enable_auth = bool(enable_auth)
        self.api_key = str(api_key or "")
        self.server_name = server_name

        self.httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._running:
            print("[WEB_API] Server already running")
            return

        handler_class = self._make_handler()
        self.httpd = ThreadingHTTPServer((self.host, self.port), handler_class)
        self._running = True

        self._thread = threading.Thread(
            target=self.httpd.serve_forever,
            name="EMSWebAPIServerThread",
            daemon=True,
        )
        self._thread.start()

        print(
            f"[WEB_API] EMS Web API server started | "
            f"http://{self.host}:{self.port} | auth={'enabled' if self.enable_auth else 'disabled'}"
        )

    def stop(self) -> None:
        if not self._running:
            return

        self._running = False

        if self.httpd is not None:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass

        if self._thread is not None:
            self._thread.join(timeout=2)

        print("[WEB_API] EMS Web API server stopped")

    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> JsonDict:
        return {
            "server_name": self.server_name,
            "running": self._running,
            "host": self.host,
            "port": self.port,
            "stream_interval_sec": self.stream_interval_sec,
            "auth_enabled": self.enable_auth,
        }

    # ------------------------------------------------------------------
    # Handler factory
    # ------------------------------------------------------------------
    def _make_handler(self):
        parent = self

        class EMSWebAPIRequestHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                print(f"[WEB_API] {self.address_string()} - {format % args}")

            # ----------------------------------------------------------
            # Common helpers
            # ----------------------------------------------------------
            @staticmethod
            def _now() -> str:
                return datetime.now().astimezone().isoformat(timespec="seconds")

            @staticmethod
            def _q(query: Dict[str, Any], key: str, default=None):
                return query.get(key, [default])[0]

            def _cors_headers(self) -> None:
                self.send_header("Access-Control-Allow-Origin", parent.cors_allow_origin)
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header(
                    "Access-Control-Allow-Headers",
                    "Content-Type, X-API-Key, X-Authorization, Authorization",
                )
                self.send_header("Cache-Control", "no-cache")

            def _send_json(self, data: JsonDict, status_code: int = 200) -> None:
                body = json.dumps(data, default=str, indent=2).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._cors_headers()
                self.end_headers()
                self.wfile.write(body)

            def _error(
                self,
                message: str,
                status_code: int = 400,
                error_code: str = "REQUEST_ERROR",
                extra: Optional[JsonDict] = None,
            ) -> None:
                payload: JsonDict = {
                    "status": "error",
                    "error_code": error_code,
                    "message": message,
                    "timestamp": self._now(),
                }
                if extra:
                    payload.update(extra)
                self._send_json(payload, status_code=status_code)

            def _is_authorized(self) -> bool:
                if not parent.enable_auth:
                    return True
                received_key = self.headers.get("X-API-Key", "")
                return bool(parent.api_key) and received_key == parent.api_key

            def _require_auth_for_write(self) -> bool:
                if self._is_authorized():
                    return True
                self._error(
                    "Missing or invalid API key",
                    status_code=401,
                    error_code="UNAUTHORIZED",
                )
                return False

            def _read_json_body(self) -> JsonDict:
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                if content_length <= 0:
                    return {}
                raw_body = self.rfile.read(content_length).decode("utf-8")
                if not raw_body.strip():
                    return {}
                try:
                    parsed = json.loads(raw_body)
                except json.JSONDecodeError as error:
                    raise ValueError(f"Invalid JSON body: {error}") from error
                if not isinstance(parsed, dict):
                    raise ValueError("JSON body must be an object")
                return parsed

            # ----------------------------------------------------------
            # Data helpers
            # ----------------------------------------------------------
            @staticmethod
            def _normalize_asset_key(asset_id: str) -> str:
                asset = str(asset_id or "").strip().lower()
                if asset in {"bms", "bms_1"}:
                    return "bms"
                if asset in {"pcs", "pcs_1", "inverter", "inverter_1"}:
                    return "pcs"
                if asset in {"chiller", "chiller_1"}:
                    return "chiller"
                return asset

            @staticmethod
            def _asset_id_from_key(asset_key: str, status_packet: Optional[JsonDict] = None) -> str:
                status_packet = status_packet or {}
                if asset_key == "bms":
                    return str(status_packet.get("bms", {}).get("asset_id") or "bms_1")
                if asset_key == "pcs":
                    return str(status_packet.get("pcs", {}).get("asset_id") or "pcs_1")
                if asset_key == "chiller":
                    return str(status_packet.get("chiller", {}).get("asset_id") or "chiller_1")
                return asset_key

            def _safe_gateway_status(self) -> JsonDict:
                try:
                    status = parent.get_status_callback()
                    if isinstance(status, dict):
                        return status
                    return {"status": "error", "message": "Gateway status callback returned non-dict"}
                except Exception as error:
                    return {"status": "error", "message": str(error), "timestamp": self._now()}

            def _safe_telemetry(self) -> JsonDict:
                try:
                    telemetry = parent.get_telemetry_callback()
                    if isinstance(telemetry, dict):
                        return telemetry
                    return {"status": "error", "message": "Telemetry callback returned non-dict"}
                except Exception as error:
                    return {"status": "error", "message": str(error), "timestamp": self._now()}

            def _extract_asset_packet(self, asset_id: str, telemetry: Optional[JsonDict] = None) -> Tuple[str, Optional[JsonDict]]:
                asset_key = self._normalize_asset_key(asset_id)
                telemetry = telemetry or self._safe_telemetry()
                assets = telemetry.get("assets", {}) if isinstance(telemetry, dict) else {}

                if isinstance(assets, dict):
                    direct = assets.get(asset_key) or assets.get(asset_id)
                    if isinstance(direct, dict):
                        return asset_key, direct

                # Backward-compatible top-level packets from current main.py
                if asset_key == "bms" and isinstance(telemetry.get("bms"), dict):
                    return asset_key, telemetry.get("bms")
                if asset_key == "pcs" and isinstance(telemetry.get("pcs"), dict):
                    return asset_key, telemetry.get("pcs")
                if asset_key == "chiller":
                    if str(telemetry.get("asset_id", "")).lower() in {"chiller_1", "chiller"}:
                        return asset_key, telemetry
                    if isinstance(assets, dict) and isinstance(assets.get("chiller"), dict):
                        return asset_key, assets.get("chiller")

                return asset_key, None

            @staticmethod
            def _is_asset_online(asset_key: str, asset_packet: Optional[JsonDict], status_packet: Optional[JsonDict]) -> bool:
                if not asset_packet:
                    return False

                status_texts: List[str] = []
                for key in ["status", "communication_status", "comm_status", "modbus_status"]:
                    value = asset_packet.get(key)
                    if value is not None:
                        status_texts.append(str(value).lower())
                data = asset_packet.get("data")
                if isinstance(data, dict):
                    for key in ["communication_status", "comm_status", "modbus_status"]:
                        value = data.get(key)
                        if value is not None:
                            status_texts.append(str(value).lower())

                if any(text in {"offline", "error", "lost", "failed"} for text in status_texts):
                    return False
                if any(text in {"online", "ok", "connected", "success"} for text in status_texts):
                    return True

                if status_packet and isinstance(status_packet.get(asset_key), dict):
                    return bool(status_packet[asset_key].get("running"))

                return True

            def _build_asset_list(self) -> JsonDict:
                status_packet = self._safe_gateway_status()
                telemetry = self._safe_telemetry()

                asset_defs = [
                    ("bms", "bms", "modbus_tcp"),
                    ("pcs", "pcs", "modbus_tcp"),
                    ("chiller", "chiller", "modbus_rtu"),
                ]
                assets: List[JsonDict] = []

                for asset_key, asset_type, protocol in asset_defs:
                    section = status_packet.get(asset_key, {}) if isinstance(status_packet.get(asset_key), dict) else {}
                    asset_id = self._asset_id_from_key(asset_key, status_packet)
                    _, asset_packet = self._extract_asset_packet(asset_id, telemetry)
                    enabled = bool(section.get("enabled", asset_packet is not None))
                    running = bool(section.get("running", asset_packet is not None))
                    assets.append(
                        {
                            "asset_id": asset_id,
                            "asset_key": asset_key,
                            "asset_type": asset_type,
                            "protocol": protocol,
                            "enabled": enabled,
                            "running": running,
                            "online": self._is_asset_online(asset_key, asset_packet, status_packet),
                        }
                    )

                return {
                    "status": "ok",
                    "gateway_id": status_packet.get("gateway_id"),
                    "timestamp": self._now(),
                    "assets_count": len(assets),
                    "assets": assets,
                }

            @staticmethod
            def _flatten_keys(value: Any, prefix: str = "") -> List[str]:
                keys: List[str] = []
                if isinstance(value, dict):
                    for key, child in value.items():
                        text_key = str(key)
                        child_prefix = f"{prefix}.{text_key}" if prefix else text_key
                        if isinstance(child, dict):
                            keys.extend(EMSWebAPIRequestHandler._flatten_keys(child, child_prefix))
                        elif isinstance(child, list):
                            keys.append(child_prefix)
                        else:
                            keys.append(child_prefix)
                return sorted(set(keys))

            def _telemetry_keys_response(self, asset_id: str) -> JsonDict:
                asset_key, packet = self._extract_asset_packet(asset_id)
                status_packet = self._safe_gateway_status()
                resolved_asset_id = self._asset_id_from_key(asset_key, status_packet)

                if packet is None:
                    return {
                        "status": "error",
                        "asset_id": asset_id,
                        "message": f"No telemetry available for asset: {asset_id}",
                        "keys": [],
                        "groups": {},
                    }

                data = packet.get("data", packet)
                keys = self._flatten_keys(data)

                groups: JsonDict = {"all": keys}
                if asset_key == "bms":
                    groups = {
                        "stack_level": [k for k in keys if any(x in k.lower() for x in ["stack", "pack", "soc", "soh"])],
                        "voltage_current_power": [k for k in keys if any(x in k.lower() for x in ["volt", "curr", "power"])],
                        "temperature": [k for k in keys if "temp" in k.lower()],
                        "alarms_status": [k for k in keys if any(x in k.lower() for x in ["alarm", "fault", "status", "state", "communication"])],
                        "all": keys,
                    }
                elif asset_key == "pcs":
                    groups = {
                        "dc_side": [k for k in keys if "dc" in k.lower()],
                        "ac_side": [k for k in keys if any(x in k.lower() for x in ["ac", "grid", "frequency", "freq", "hz"])],
                        "power_energy": [k for k in keys if any(x in k.lower() for x in ["power", "kw", "kwh", "energy", "reactive"])],
                        "status_faults": [k for k in keys if any(x in k.lower() for x in ["status", "fault", "alarm", "comm"])],
                        "all": keys,
                    }
                elif asset_key == "chiller":
                    groups = {
                        "temperature": [k for k in keys if "temp" in k.lower()],
                        "pressure": [k for k in keys if "pressure" in k.lower()],
                        "control": [k for k in keys if any(x in k.lower() for x in ["mode", "set", "on", "off", "enable"])],
                        "status_faults": [k for k in keys if any(x in k.lower() for x in ["status", "fault", "error", "communication"])],
                        "all": keys,
                    }

                return {
                    "status": "ok",
                    "asset_id": resolved_asset_id,
                    "asset_type": asset_key,
                    "keys_count": len(keys),
                    "keys": keys,
                    "groups": groups,
                    "timestamp": self._now(),
                }

            @staticmethod
            def _timestamp_to_ms(value: Any) -> Optional[int]:
                if value is None:
                    return None
                text = str(value).strip()
                if not text:
                    return None
                if text.isdigit():
                    number = int(text)
                    return number if number > 10_000_000_000 else number * 1000
                normalized = text.replace("Z", "+00:00")
                try:
                    return int(datetime.fromisoformat(normalized).timestamp() * 1000)
                except Exception:
                    return None

            def _timeseries_response(self, asset_id: str, query: Dict[str, Any]) -> JsonDict:
                if parent.log_query_service is None:
                    return {
                        "status": "error",
                        "error_code": "LOG_QUERY_SERVICE_UNAVAILABLE",
                        "message": "Log query service is not available",
                        "asset_id": asset_id,
                    }

                keys = self._q(query, "keys") or self._q(query, "fields")
                limit = self._q(query, "limit", 100)
                date = self._q(query, "date")
                start_time = self._q(query, "start_time")
                end_time = self._q(query, "end_time")

                start_ts = self._q(query, "startTs")
                end_ts = self._q(query, "endTs")

                # If only startTs/endTs are provided, infer the local date from startTs.
                if date is None and start_ts:
                    try:
                        date = datetime.fromtimestamp(int(start_ts) / 1000).astimezone().date().isoformat()
                    except Exception:
                        date = None

                if date is None:
                    return {
                        "status": "error",
                        "error_code": "MISSING_DATE",
                        "message": "Provide date=YYYY-MM-DD, or provide startTs for timeseries query",
                        "asset_id": asset_id,
                    }

                log_response = parent.log_query_service.get_telemetry_logs(
                    asset_id=asset_id,
                    date=date,
                    limit=limit,
                    fields=keys,
                    start_time=start_time,
                    end_time=end_time,
                )

                if log_response.get("status") != "ok":
                    return log_response

                selected_keys = [item.strip() for item in str(keys or "").split(",") if item.strip()]
                rows = log_response.get("rows", [])
                data: JsonDict = {key: [] for key in selected_keys}

                if not selected_keys and rows:
                    selected_keys = [key for key in rows[0].keys() if key != "timestamp"]
                    data = {key: [] for key in selected_keys}

                start_ms = int(start_ts) if start_ts and str(start_ts).isdigit() else None
                end_ms = int(end_ts) if end_ts and str(end_ts).isdigit() else None

                for row in rows:
                    ts_ms = self._timestamp_to_ms(row.get("timestamp"))
                    if ts_ms is None:
                        continue
                    if start_ms is not None and ts_ms < start_ms:
                        continue
                    if end_ms is not None and ts_ms > end_ms:
                        continue
                    for key in selected_keys:
                        if key in row:
                            data.setdefault(key, []).append({"ts": ts_ms, "value": row.get(key)})

                return {
                    "status": "ok",
                    "asset_id": asset_id,
                    "date": date,
                    "startTs": start_ts,
                    "endTs": end_ts,
                    "keys": selected_keys,
                    "data": data,
                    "rows_count": sum(len(values) for values in data.values()),
                    "source": "local_csv_logs",
                    "raw_log_response": {
                        "file": log_response.get("file"),
                        "total_rows": log_response.get("total_rows"),
                        "filtered_rows": log_response.get("filtered_rows"),
                        "limit": log_response.get("limit"),
                    },
                }

            # ----------------------------------------------------------
            # HTTP methods
            # ----------------------------------------------------------
            def do_OPTIONS(self):
                self.send_response(204)
                self._cors_headers()
                self.end_headers()

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/") or "/"
                query = parse_qs(parsed.query)

                try:
                    if path == "/":
                        self._send_json(
                            {
                                "status": "ok",
                                "server": parent.server_name,
                                "message": "EMS Web API Server",
                                "timestamp": self._now(),
                                "endpoints": [
                                    "/api/gateway/health",
                                    "/api/gateway/status",
                                    "/api/gateway/network",
                                    "/api/assets",
                                    "/api/assets/{asset_id}",
                                    "/api/telemetry/latest",
                                    "/api/assets/{asset_id}/telemetry/latest",
                                    "/api/assets/{asset_id}/telemetry/keys",
                                    "/api/assets/{asset_id}/telemetry/timeseries?keys=key1,key2&date=YYYY-MM-DD&limit=100",
                                    "/api/stream/telemetry",
                                    "/api/commands",
                                    "/api/assets/{asset_id}/commands",
                                ],
                            }
                        )
                        return

                    if path in {"/api/health", "/api/gateway/health"}:
                        self._send_json(
                            {
                                "status": "ok",
                                "server": parent.server_name,
                                "message": "EMS Web API server running",
                                "timestamp": self._now(),
                                "host": parent.host,
                                "port": parent.port,
                            }
                        )
                        return

                    if path == "/api/gateway/status":
                        gateway_status = self._safe_gateway_status()
                        self._send_json(
                            {
                                "status": "ok" if gateway_status.get("status") != "error" else "error",
                                "timestamp": self._now(),
                                "gateway": gateway_status,
                                "web_api_server": parent.get_status(),
                            }
                        )
                        return

                    if path == "/api/gateway/network":
                        gateway_status = self._safe_gateway_status()
                        self._send_json(
                            {
                                "status": "ok",
                                "timestamp": self._now(),
                                "network": gateway_status.get("network", {}),
                                "web_api_server": parent.get_status(),
                                "note": "Wi-Fi/Ethernet IP configuration is handled by Linux OS, not by EMS main.py",
                            }
                        )
                        return

                    if path == "/api/assets":
                        self._send_json(self._build_asset_list())
                        return

                    if path == "/api/telemetry/latest":
                        telemetry = self._safe_telemetry()
                        self._send_json(telemetry)
                        return

                    if path == "/api/stream/telemetry":
                        self._handle_sse_stream()
                        return

                    parts = [part for part in path.split("/") if part]
                    # /api/assets/{asset_id}
                    # /api/assets/{asset_id}/telemetry/latest
                    # /api/assets/{asset_id}/telemetry/keys
                    # /api/assets/{asset_id}/telemetry/timeseries
                    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "assets":
                        asset_id = parts[2]

                        if len(parts) == 3:
                            assets_response = self._build_asset_list()
                            for asset in assets_response.get("assets", []):
                                if str(asset.get("asset_id", "")).lower() == asset_id.lower() or str(asset.get("asset_key", "")).lower() == asset_id.lower():
                                    self._send_json({"status": "ok", "asset": asset, "timestamp": self._now()})
                                    return
                            self._error(f"Asset not found: {asset_id}", status_code=404, error_code="INVALID_ASSET")
                            return

                        if len(parts) == 5 and parts[3] == "telemetry" and parts[4] == "latest":
                            telemetry = self._safe_telemetry()
                            asset_key, packet = self._extract_asset_packet(asset_id, telemetry)
                            if packet is None:
                                self._error(f"No telemetry available for asset: {asset_id}", status_code=404, error_code="ASSET_TELEMETRY_NOT_FOUND")
                                return
                            status_packet = self._safe_gateway_status()
                            self._send_json(
                                {
                                    "status": "ok",
                                    "asset_id": self._asset_id_from_key(asset_key, status_packet),
                                    "asset_type": asset_key,
                                    "timestamp": telemetry.get("timestamp", self._now()),
                                    "online": self._is_asset_online(asset_key, packet, status_packet),
                                    "telemetry": packet,
                                }
                            )
                            return

                        if len(parts) == 5 and parts[3] == "telemetry" and parts[4] == "keys":
                            self._send_json(self._telemetry_keys_response(asset_id))
                            return

                        if len(parts) == 5 and parts[3] == "telemetry" and parts[4] == "timeseries":
                            self._send_json(self._timeseries_response(asset_id, query))
                            return

                    self._error(f"Endpoint not found: {path}", status_code=404, error_code="NOT_FOUND")

                except BrokenPipeError:
                    # Client disconnected during response.
                    return
                except Exception as error:
                    self._error(str(error), status_code=500, error_code="INTERNAL_ERROR")

            def do_POST(self):
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/") or "/"

                try:
                    if not self._require_auth_for_write():
                        return

                    body = self._read_json_body()
                    parts = [part for part in path.split("/") if part]

                    command_packet: JsonDict
                    if path == "/api/commands":
                        command_packet = dict(body)
                        if not command_packet.get("asset_id") and not command_packet.get("asset_type"):
                            self._error("Missing asset_id or asset_type", status_code=400, error_code="MISSING_ASSET")
                            return

                    elif len(parts) == 4 and parts[0] == "api" and parts[1] == "assets" and parts[3] == "commands":
                        asset_id = parts[2]
                        command_packet = dict(body)
                        command_packet["asset_id"] = asset_id
                    else:
                        self._error(f"Endpoint not found: {path}", status_code=404, error_code="NOT_FOUND")
                        return

                    command = str(command_packet.get("command", "")).strip().upper()
                    if not command:
                        self._error("Missing command", status_code=400, error_code="MISSING_COMMAND")
                        return
                    command_packet["command"] = command
                    command_packet.setdefault("request_id", f"web-{int(time.time() * 1000)}")
                    command_packet["client"] = self.client_address[0]
                    command_packet["source"] = f"web_api:{self.client_address[0]}"

                    result = parent.execute_command_callback(command_packet)
                    if not isinstance(result, dict):
                        result = {
                            "status": "error",
                            "message": "Command callback returned non-dict response",
                            "data": result,
                        }

                    status_code = 200 if str(result.get("status", "")).lower() == "ok" else 400
                    response = {
                        "status": result.get("status", "ok"),
                        "timestamp": self._now(),
                        "asset_id": command_packet.get("asset_id"),
                        "command": command,
                        "request_id": command_packet.get("request_id"),
                        "result": result,
                    }
                    self._send_json(response, status_code=status_code)

                except ValueError as error:
                    self._error(str(error), status_code=400, error_code="INVALID_REQUEST_BODY")
                except Exception as error:
                    self._error(str(error), status_code=500, error_code="INTERNAL_ERROR")

            def _handle_sse_stream(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Accel-Buffering", "no")
                self._cors_headers()
                self.end_headers()

                try:
                    # Initial event
                    self.wfile.write(b": EMS telemetry stream connected\n\n")
                    self.wfile.flush()

                    while parent._running:
                        telemetry = self._safe_telemetry()
                        payload = json.dumps(telemetry, default=str)
                        event_text = f"event: telemetry\ndata: {payload}\n\n".encode("utf-8")
                        self.wfile.write(event_text)
                        self.wfile.flush()
                        time.sleep(parent.stream_interval_sec)
                except (BrokenPipeError, ConnectionResetError):
                    return
                except Exception as error:
                    try:
                        payload = json.dumps(
                            {
                                "status": "error",
                                "message": str(error),
                                "timestamp": self._now(),
                            }
                        )
                        self.wfile.write(f"event: error\ndata: {payload}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    except Exception:
                        pass

        return EMSWebAPIRequestHandler
