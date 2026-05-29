"""
HTTP Log API Server for i.MX93 EMS Gateway.

Purpose:
- Expose eMMC/SD card logs to Flutter dashboard over HTTP.
- Provide REST APIs for telemetry logs, event logs, error logs, metadata, and storage status.
- Support filters for date, time range, fields, status, event type, error type, source, and search.
- Uses only Python standard library, so no Flask/FastAPI dependency is required.
"""

import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse


class LogHTTPServer:
    def __init__(
        self,
        host: str,
        port: int,
        log_query_service,
        server_name: str = "ems_log_http_server",
    ):
        self.host = host
        self.port = int(port)
        self.log_query_service = log_query_service
        self.server_name = server_name

        self.httpd = None
        self._thread = None
        self._running = False

    def start(self) -> None:
        if self._running:
            print("[LOG_HTTP] Server already running")
            return

        handler_class = self._make_handler()

        self.httpd = ThreadingHTTPServer(
            (self.host, self.port),
            handler_class,
        )

        self._running = True

        self._thread = threading.Thread(
            target=self.httpd.serve_forever,
            name="LogHTTPServerThread",
            daemon=True,
        )

        self._thread.start()

        print(
            f"[LOG_HTTP] Log HTTP server started | "
            f"http://{self.host}:{self.port}"
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

        print("[LOG_HTTP] Log HTTP server stopped")

    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> Dict[str, Any]:
        return {
            "server_name": self.server_name,
            "running": self._running,
            "host": self.host,
            "port": self.port,
        }

    def _make_handler(self):
        log_query_service = self.log_query_service
        server_name = self.server_name

        class LogRequestHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                print(f"[LOG_HTTP] {self.address_string()} - {format % args}")

            @staticmethod
            def _q(query: Dict[str, Any], key: str, default=None):
                return query.get(key, [default])[0]

            def _send_json(self, data: Dict[str, Any], status_code: int = 200) -> None:
                body = json.dumps(data, default=str, indent=2).encode("utf-8")

                self.send_response(status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()
                self.wfile.write(body)

            def _send_file_download(self, file_path, download_name: str) -> None:
                with open(file_path, mode="rb") as file:
                    body = file.read()

                self.send_response(200)
                self.send_header("Content-Type", "text/csv")
                self.send_header("Content-Length", str(len(body)))
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="{download_name}"',
                )
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def _error(self, message: str, status_code: int = 400) -> None:
                self._send_json(
                    {
                        "status": "error",
                        "message": message,
                        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                    },
                    status_code=status_code,
                )

            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path
                query = parse_qs(parsed.query)

                try:
                    if path == "/":
                        self._send_json(
                            {
                                "status": "ok",
                                "server": server_name,
                                "message": "EMS Log HTTP API Server",
                                "endpoints": [
                                    "/api/health",
                                    "/api/storage/status",
                                    "/api/logs/files",
                                    "/api/logs/telemetry?date=YYYY-MM-DD&limit=100&start_time=HH:MM:SS&end_time=HH:MM:SS&fields=timestamp,outlet_water_temp",
                                    "/api/logs/events?date=YYYY-MM-DD&event_type=SET_TEMPERATURE_WRITE&status=success&limit=100",
                                    "/api/logs/errors?date=YYYY-MM-DD&error_type=SETTINGS_READ_FAILED&limit=100",
                                    "/api/logs/metadata",
                                    "/api/logs/download/telemetry?date=YYYY-MM-DD",
                                ],
                            }
                        )
                        return

                    if path == "/api/health":
                        self._send_json(
                            {
                                "status": "ok",
                                "server": server_name,
                                "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                            }
                        )
                        return

                    if path == "/api/storage/status":
                        self._send_json(log_query_service.get_storage_status())
                        return

                    if path == "/api/logs/files":
                        self._send_json(log_query_service.list_telemetry_files())
                        return

                    if path == "/api/logs/telemetry":
                        date = self._q(query, "date")
                        limit = self._q(query, "limit", 100)

                        if date is None:
                            self._error("Missing required query parameter: date")
                            return

                        self._send_json(
                            log_query_service.get_telemetry_logs(
                                date=date,
                                limit=limit,
                                start_time=self._q(query, "start_time"),
                                end_time=self._q(query, "end_time"),
                                fields=self._q(query, "fields"),
                                modbus_status=self._q(query, "modbus_status"),
                                logger_status=self._q(query, "logger_status"),
                                search=self._q(query, "search"),
                            )
                        )
                        return

                    if path == "/api/logs/events":
                        limit = self._q(query, "limit", 100)

                        self._send_json(
                            log_query_service.get_event_logs(
                                limit=limit,
                                date=self._q(query, "date"),
                                start_time=self._q(query, "start_time"),
                                end_time=self._q(query, "end_time"),
                                event_type=self._q(query, "event_type"),
                                status=self._q(query, "status"),
                                source=self._q(query, "source"),
                                search=self._q(query, "search"),
                                fields=self._q(query, "fields"),
                            )
                        )
                        return

                    if path == "/api/logs/errors":
                        limit = self._q(query, "limit", 100)

                        self._send_json(
                            log_query_service.get_error_logs(
                                limit=limit,
                                date=self._q(query, "date"),
                                start_time=self._q(query, "start_time"),
                                end_time=self._q(query, "end_time"),
                                error_type=self._q(query, "error_type"),
                                error_source=self._q(query, "error_source"),
                                search=self._q(query, "search"),
                                fields=self._q(query, "fields"),
                            )
                        )
                        return

                    if path == "/api/logs/metadata":
                        self._send_json(log_query_service.get_metadata())
                        return

                    if path == "/api/logs/download/telemetry":
                        date = self._q(query, "date")

                        if date is None:
                            self._error("Missing required query parameter: date")
                            return

                        file_path = log_query_service.get_telemetry_csv_download_path(date)

                        self._send_file_download(
                            file_path=file_path,
                            download_name=f"chiller_telemetry_{date}.csv",
                        )
                        return

                    self._error(f"Unknown endpoint: {path}", status_code=404)

                except FileNotFoundError as error:
                    self._error(str(error), status_code=404)

                except Exception as error:
                    self._error(str(error), status_code=500)

        return LogRequestHandler