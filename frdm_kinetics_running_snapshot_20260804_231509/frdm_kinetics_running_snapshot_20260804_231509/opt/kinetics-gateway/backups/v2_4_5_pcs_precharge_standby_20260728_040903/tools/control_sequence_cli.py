#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


def request_json(url: str, *, method: str = "GET", token: str | None = None, payload: dict[str, Any] | None = None) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {body}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Request failed: {error}") from error


def login(base_url: str, username: str, password: str) -> str:
    payload = request_json(
        f"{base_url}/api/auth/login",
        method="POST",
        payload={"username": username, "password": password},
    )
    return str(payload["access_token"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Kinetics staged BMS/PCS control API client")
    parser.add_argument("command", choices=[
        "capabilities", "status", "precheck", "enable-rack", "start-insulation",
        "verify-insulation", "start-precharge", "recover-bms", "verify-ready",
        "configure-pcs", "start-pcs", "set-power",
        "verify-power", "safe-stop",
    ])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="internal")
    parser.add_argument("--password", default="Internal@123")
    parser.add_argument("--pair-id", default="pair_1")
    parser.add_argument("--direction", choices=["charge", "discharge"])
    parser.add_argument("--power-kw", type=float)
    parser.add_argument("--confirmation", default="")
    parser.add_argument("--open-bms", action="store_true")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    token = login(base, args.username, args.password)
    pair = args.pair_id

    if args.command == "capabilities":
        result = request_json(f"{base}/api/control-sequence/capabilities", token=token)
    elif args.command == "status":
        result = request_json(f"{base}/api/control-sequence/{pair}/status?fresh=true", token=token)
    elif args.command == "precheck":
        if args.direction is None or args.power_kw is None:
            parser.error("precheck requires --direction and --power-kw")
        result = request_json(
            f"{base}/api/control-sequence/{pair}/precheck",
            method="POST", token=token,
            payload={"direction": args.direction, "power_kw": args.power_kw},
        )
    elif args.command == "enable-rack":
        if args.direction is None or args.power_kw is None:
            parser.error("enable-rack requires --direction and --power-kw")
        result = request_json(
            f"{base}/api/control-sequence/{pair}/enable-rack",
            method="POST", token=token,
            payload={
                "direction": args.direction,
                "power_kw": args.power_kw,
                "confirmation": args.confirmation,
            },
        )
    elif args.command in {"start-insulation", "start-precharge", "recover-bms", "configure-pcs", "start-pcs"}:
        endpoint = {
            "start-insulation": "start-insulation",
            "start-precharge": "start-precharge",
            "recover-bms": "recover-bms",
            "configure-pcs": "configure-pcs",
            "start-pcs": "start-pcs",
        }[args.command]
        result = request_json(
            f"{base}/api/control-sequence/{pair}/{endpoint}",
            method="POST", token=token,
            payload={"confirmation": args.confirmation},
        )
    elif args.command == "verify-insulation":
        result = request_json(f"{base}/api/control-sequence/{pair}/verify-insulation", token=token)
    elif args.command == "verify-ready":
        result = request_json(f"{base}/api/control-sequence/{pair}/verify-ready", token=token)
    elif args.command == "set-power":
        if args.direction is None or args.power_kw is None:
            parser.error("set-power requires --direction and --power-kw")
        result = request_json(
            f"{base}/api/control-sequence/{pair}/set-power",
            method="POST", token=token,
            payload={
                "direction": args.direction,
                "power_kw": args.power_kw,
                "confirmation": args.confirmation,
            },
        )
    elif args.command == "verify-power":
        result = request_json(f"{base}/api/control-sequence/{pair}/verify-power", token=token)
    elif args.command == "safe-stop":
        result = request_json(
            f"{base}/api/control-sequence/{pair}/safe-stop",
            method="POST", token=token,
            payload={"confirmation": args.confirmation, "open_bms": args.open_bms},
        )
    else:
        raise AssertionError(args.command)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
