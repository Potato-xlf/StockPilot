from app.main import app
from fastapi.testclient import TestClient


class FakeResult:
    pass


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def execute(self, statement):
        return FakeResult()


def test_health(monkeypatch):
    monkeypatch.setattr("app.main.SessionLocal", lambda: FakeSession())
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
