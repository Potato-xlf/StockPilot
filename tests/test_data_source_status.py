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
