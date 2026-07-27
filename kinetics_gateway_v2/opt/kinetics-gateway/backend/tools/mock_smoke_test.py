#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("KINETICS_CONFIG", "configs/kinetics_mock.json")

from fastapi.testclient import TestClient
from app.main import app


def main() -> int:
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "internal", "password": "Internal@123"})
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        for scenario in client.get("/api/mock/scenarios", headers=headers).json()["scenarios"]:
            response = client.post(f"/api/mock/scenario/{scenario}", headers=headers)
            response.raise_for_status()
            snapshot = response.json()["snapshot"]
            print(
                scenario,
                "assets=", len(client.get("/api/assets", headers=headers).json()["assets"]),
                "alarms=", len(snapshot.get("alarms", [])),
                "racks=", len(snapshot["racks"]),
                "pcs_points=", len(snapshot["pcs"]["telemetry"]),
                "pcs_devices=", len(snapshot.get("pcs_devices", {})),
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
