#!/usr/bin/env python3

import argparse
import json
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


def parse_iso(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


class EdgeAIHandler(BaseHTTPRequestHandler):
    latest_json_path = None
    jsonl_path = None
    stale_after_sec = 30.0
    started_at = time.time()

    def _send_json(self, status, payload):
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status, html):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _load_latest(self):
        p = Path(self.latest_json_path)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def _latest_age_sec(self, latest):
        dt = parse_iso(latest.get("cycle_time") if latest else None)
        if not dt:
            return None
        now = datetime.now(timezone.utc)
        return round((now - dt.astimezone(timezone.utc)).total_seconds(), 2)

    def _summary(self, latest):
        if latest is None:
            return {
                "ok": False,
                "edge_ai_status": "NO_DATA",
                "error": "latest_ml_health_json_not_found",
                "latest_json_path": str(self.latest_json_path),
            }

        age = self._latest_age_sec(latest)
        stale = age is None or age > self.stale_after_sec

        sources = {}
        any_anomaly = False

        for source_id, src in latest.get("sources", {}).items():
            pred = bool(src.get("ml_predicted_anomaly"))
            any_anomaly = any_anomaly or pred
            sources[source_id] = {
                "ok": src.get("ok"),
                "bess_id": src.get("bess_id"),
                "status": "ANOMALY" if pred else "NORMAL",
                "ml_predicted_anomaly": pred,
                "anomaly_score_ml": src.get("anomaly_score_ml"),
                "threshold": src.get("threshold"),
                "inference_latency_ms": src.get("inference_latency_ms"),
                "key_features": src.get("key_features", {}),
            }

        if stale:
            edge_ai_status = "STALE"
        elif any_anomaly:
            edge_ai_status = "ANOMALY"
        else:
            edge_ai_status = "NORMAL"

        model_info = latest.get("model_info", {})
        if not model_info:
            model_info = {
                "model_type": latest.get("model_type"),
                "runtime_format": latest.get("runtime_format"),
                "preprocessor": latest.get("preprocessor"),
                "feature_count": latest.get("feature_count"),
                "threshold": latest.get("threshold"),
            }

        return {
            "ok": bool(latest.get("ok", False)) and not stale,
            "edge_ai_status": edge_ai_status,
            "phase": latest.get("phase"),
            "cycle_time": latest.get("cycle_time"),
            "cycle_index": latest.get("cycle_index"),
            "latest_age_sec": age,
            "stale_after_sec": self.stale_after_sec,
            "cycle_latency_ms": latest.get("cycle_latency_ms"),
            "model_info": model_info,
            "sources": sources,
        }

    def _dashboard_html(self, summary):
        rows = ""

        for source_id, src in summary.get("sources", {}).items():
            status = src.get("status")
            cls = "anomaly" if status == "ANOMALY" else "normal"
            k = src.get("key_features", {})

            rows += f"""
            <tr>
              <td>{source_id}</td>
              <td>{src.get("bess_id")}</td>
              <td class="{cls}">{status}</td>
              <td>{src.get("anomaly_score_ml")}</td>
              <td>{src.get("threshold")}</td>
              <td>{src.get("inference_latency_ms")} ms</td>
              <td>{k.get("bms_cell_voltage_spread")}</td>
              <td>{k.get("bms_temperature_spread")}</td>
              <td>{k.get("pcs_dc_voltage_vs_bms_voltage_delta")}</td>
              <td>{k.get("pcs_dc_current_vs_bms_current_delta")}</td>
            </tr>
            """

        model = summary.get("model_info", {})

        return f"""<!doctype html>
<html>
<head>
  <title>Edge AI Health</title>
  <meta http-equiv="refresh" content="5">
  <style>
    body {{
      background: #101214;
      color: #e8e8e8;
      font-family: Arial, sans-serif;
      padding: 28px;
    }}
    .card {{
      background: #181b1f;
      border: 1px solid #30353b;
      border-radius: 12px;
      padding: 18px;
      margin-bottom: 18px;
    }}
    h1 {{ margin: 0 0 8px 0; }}
    .status {{
      display: inline-block;
      padding: 8px 14px;
      border-radius: 999px;
      font-weight: bold;
      margin-top: 8px;
    }}
    .NORMAL {{ background: #103d2b; color: #4df0a0; }}
    .ANOMALY {{ background: #451818; color: #ff7777; }}
    .STALE {{ background: #4b3a10; color: #ffd86b; }}
    .NO_DATA {{ background: #333; color: #ddd; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      border-bottom: 1px solid #30353b;
      padding: 10px;
      text-align: left;
    }}
    th {{ color: #9fb3c8; }}
    .normal {{ color: #4df0a0; font-weight: bold; }}
    .anomaly {{ color: #ff7777; font-weight: bold; }}
    code {{ color: #9fd0ff; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Edge AI Live Health</h1>
    <div>Live PCS/BMS telemetry → 33 features → on-device ML inference</div>
    <div class="status {summary.get("edge_ai_status")}">{summary.get("edge_ai_status")}</div>
  </div>

  <div class="card">
    <b>Model:</b> {model.get("model_type")} |
    <b>Runtime:</b> {model.get("runtime_format")} |
    <b>Preprocessor:</b> {model.get("preprocessor")} |
    <b>Features:</b> {model.get("feature_count")} |
    <b>Threshold:</b> {model.get("threshold")}
    <br>
    <b>Cycle:</b> {summary.get("cycle_index")} |
    <b>Last update:</b> {summary.get("cycle_time")} |
    <b>Age:</b> {summary.get("latest_age_sec")} sec |
    <b>Cycle latency:</b> {summary.get("cycle_latency_ms")} ms
  </div>

  <div class="card">
    <table>
      <tr>
        <th>Source</th>
        <th>BESS</th>
        <th>Status</th>
        <th>ML Score</th>
        <th>Threshold</th>
        <th>Latency</th>
        <th>Cell V Spread</th>
        <th>Temp Spread</th>
        <th>PCS-BMS V Δ</th>
        <th>PCS-BMS I Δ</th>
      </tr>
      {rows}
    </table>
  </div>

  <div class="card">
    API: <code>/api/edge-ai/summary</code> |
    <code>/api/edge-ai/latest</code> |
    <code>/api/edge-ai/source/external_ems_1</code> |
    <code>/api/edge-ai/source/external_ems_2</code>
  </div>
</body>
</html>
"""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            latest = self._load_latest()

            if path == "/":
                summary = self._summary(latest)
                return self._send_html(200, self._dashboard_html(summary))

            if path == "/api/edge-ai/health":
                latest_exists = Path(self.latest_json_path).exists()
                summary = self._summary(latest)
                payload = {
                    "ok": True,
                    "service": "edge-ai-api",
                    "phase": "9",
                    "uptime_sec": round(time.time() - self.started_at, 2),
                    "latest_json_exists": latest_exists,
                    "latest_json_path": str(self.latest_json_path),
                    "jsonl_path": str(self.jsonl_path),
                    "edge_ai_status": summary.get("edge_ai_status"),
                    "latest_age_sec": summary.get("latest_age_sec"),
                    "stale_after_sec": self.stale_after_sec,
                }
                return self._send_json(200, payload)

            if path == "/api/edge-ai/summary":
                return self._send_json(200, self._summary(latest))

            if path == "/api/edge-ai/latest":
                if latest is None:
                    return self._send_json(503, {
                        "ok": False,
                        "error": "latest_ml_health_json_not_found",
                        "path": str(self.latest_json_path),
                    })
                return self._send_json(200, latest)

            if path.startswith("/api/edge-ai/source/"):
                source_id = path.split("/api/edge-ai/source/", 1)[1].strip("/")
                if latest is None:
                    return self._send_json(503, {
                        "ok": False,
                        "error": "latest_ml_health_json_not_found",
                    })

                source_payload = latest.get("sources", {}).get(source_id)

                if source_payload is None:
                    return self._send_json(404, {
                        "ok": False,
                        "error": "source_not_found",
                        "source_id": source_id,
                        "available_sources": sorted(list(latest.get("sources", {}).keys())),
                    })

                return self._send_json(200, source_payload)

            return self._send_json(404, {
                "ok": False,
                "error": "not_found",
                "path": path,
                "available_endpoints": [
                    "/",
                    "/api/edge-ai/health",
                    "/api/edge-ai/summary",
                    "/api/edge-ai/latest",
                    "/api/edge-ai/source/external_ems_1",
                    "/api/edge-ai/source/external_ems_2",
                ],
            })

        except Exception as e:
            return self._send_json(500, {
                "ok": False,
                "error": repr(e),
            })

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8011)
    ap.add_argument("--latest-json", default="/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/live_inference_v0_3/latest_ml_health_v0_3.json")
    ap.add_argument("--jsonl", default="/mnt/ems-logs/northbound_ems_gateway/edge_ai_poc/live_inference_v0_3/phase7_2_live_inference_v0_3.jsonl")
    ap.add_argument("--stale-after-sec", type=float, default=30.0)
    args = ap.parse_args()

    EdgeAIHandler.latest_json_path = args.latest_json
    EdgeAIHandler.jsonl_path = args.jsonl
    EdgeAIHandler.stale_after_sec = args.stale_after_sec

    server = ThreadingHTTPServer((args.host, args.port), EdgeAIHandler)

    print("==============================================================")
    print(" PHASE 9 EDGE AI API + DASHBOARD")
    print("==============================================================")
    print("HOST        =", args.host)
    print("PORT        =", args.port)
    print("LATEST_JSON =", args.latest_json)
    print("JSONL       =", args.jsonl)
    print("STALE_AFTER =", args.stale_after_sec)
    print("ENDPOINTS   =")
    print("  GET /")
    print("  GET /api/edge-ai/health")
    print("  GET /api/edge-ai/summary")
    print("  GET /api/edge-ai/latest")
    print("  GET /api/edge-ai/source/external_ems_1")
    print("  GET /api/edge-ai/source/external_ems_2")
    print("==============================================================")

    server.serve_forever()


if __name__ == "__main__":
    main()
