import asyncio

from app.main import app
from fastapi.testclient import TestClient


async def healthy(_):
    return None


def test_data_source_status(monkeypatch):
    monkeypatch.setattr("app.api.v1.router.AKShareDataSource.health_check", healthy)
    with TestClient(app) as client:
        response = client.get("/api/v1/data-source/status")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["name"] == "akshare"


async def slow_health_check(_):
    await asyncio.sleep(1)


def test_data_source_status_times_out(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.router.AKShareDataSource.health_check", slow_health_check
    )
    monkeypatch.setattr("app.api.v1.router.DATA_SOURCE_STATUS_TIMEOUT_SECONDS", 0.01)

    with TestClient(app) as client:
        response = client.get("/api/v1/data-source/status")

    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert response.json()["message"] == "AKShare health check timed out after 0.01 seconds"
