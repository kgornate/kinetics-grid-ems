#!/usr/bin/env python3
"""Read-only authenticated checks; use from a terminal (password prompt)."""
import argparse
import getpass
import json
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="internal")
    parser.add_argument("--wait-history", action="store_true")
    args = parser.parse_args()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(path, data=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(args.url.rstrip("/") + path,
            data=None if data is None else json.dumps(data).encode(), headers=headers)
        with opener.open(req, timeout=10) as response:
            return json.load(response)
    token = request("/api/auth/login", {
        "username": args.username, "password": getpass.getpass("Kalpa API password: ")
    })["access_token"]
    asset = request("/api/meters/acrel_meter_1", token=token)
    print(json.dumps(asset, indent=2))
    if not asset["online"] or asset["source"] != "hardware":
        raise SystemExit("Meter is not currently online with hardware readings. Check read_errors above.")
    print("PASS: Live hardware meter API")
    for path in ("/api/assets", "/api/telemetry/snapshot", "/api/telemetry/compact"):
        result = request(path, token=token)
        if path == "/api/assets":
            assert any(a["asset_id"] == "acrel_meter_1" for a in result["assets"])
        else:
            assert "acrel_meter_1" in result["meters"]
        print("PASS:", path)
    # Existing retention/quota settings govern history sampling (often 60s on fallback storage).
    for attempt in range(75 if args.wait_history else 1):
        history = request("/api/meters/acrel_meter_1/history?limit=3", token=token)
        good = [row for row in history["samples"] if (
            row["payload"].get("online")
            and row["payload"].get("source") == "hardware"
            and (row["payload"].get("timestamp") or "") >= asset["timestamp"]
        )]
        if good:
            print("PASS: Persisted meter history; latest stored sample:", good[0]["timestamp"])
            break
        if not args.wait_history:
            print("History not sampled yet. Retry with --wait-history after the configured storage interval.")
            break
        time.sleep(2)
    else:
        raise SystemExit("No online meter history sample observed in 150 seconds; check storage interval/status.")
    if asset["status"] != "online":
        print("ATTENTION: Meter is responding but one or more points/energy blocks are degraded.")
    print("Scaling is not commissioned until compared against the meter display under measurement inputs.")


if __name__ == "__main__":
    main()
