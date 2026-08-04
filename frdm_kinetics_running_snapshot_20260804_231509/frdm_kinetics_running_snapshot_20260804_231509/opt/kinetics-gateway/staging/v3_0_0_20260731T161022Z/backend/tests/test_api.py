import os

os.environ.setdefault("KINETICS_CONFIG", "configs/kinetics_mock.json")

from fastapi.testclient import TestClient
from app.main import app


def login(client, username="internal", password="Internal@123"):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_health_and_secured_assets():
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/assets").status_code == 401
        token = login(client)
        response = client.get("/api/assets", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["count"] >= 12


def test_customer_cannot_control():
    with TestClient(app) as client:
        token = login(client, "customer", "Customer@123")
        response = client.post(
            "/api/control/bms_bank/reset",
            json={"value": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


def test_storage_events_and_exports():
    with TestClient(app) as client:
        token = login(client)
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/storage/status", headers=headers).status_code == 200
        assert client.get("/api/events", headers=headers).status_code == 200
        rate = client.get("/api/diagnostics/data-rate", headers=headers)
        assert rate.status_code == 200
        assert rate.json()["field_modbus"]["total_requests_per_minute"] > 0
        assert client.get("/api/telemetry/compact", headers=headers).status_code == 200
        capabilities = client.get("/api/control/capabilities", headers=headers)
        assert capabilities.status_code == 200
        assert capabilities.json()["counts"]["bms"] > 300
        export = client.get("/api/export/historian/bms_bank.csv", headers=headers)
        assert export.status_code == 200
        assert "text/csv" in export.headers["content-type"]


def test_background_scheduler_advances_fast_group():
    import time

    with TestClient(app) as client:
        before = client.get("/api/health").json()["polling"]["fast"]["count"]
        time.sleep(1.2)
        after = client.get("/api/health").json()["polling"]["fast"]["count"]
        assert after > before
