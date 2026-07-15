from datetime import UTC, datetime

from app.main import app
from app.services.market_insights import DataSyncRunSnapshot, SectorSyncRunSnapshot
from fastapi.testclient import TestClient


def test_sync_runs(monkeypatch):
    async def fake_sync_runs(_self, limit):
        assert limit == 2
        when = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)
        return (
            [
                DataSyncRunSnapshot(
                    id=7,
                    job_type="incremental",
                    status="completed",
                    requested_days=5,
                    stock_count=11,
                    quote_count=55,
                    failed_symbols=0,
                    message=None,
                    started_at=when,
                    finished_at=when,
                )
            ],
            [
                SectorSyncRunSnapshot(
                    id=3,
                    sector_type="industry",
                    status="partial",
                    sector_count=2,
                    member_count=0,
                    failed_sectors=1,
                    message="one sector failed",
                    started_at=when,
                    finished_at=when,
                )
            ],
        )

    monkeypatch.setattr("app.api.v1.router.MarketInsightsService.sync_runs", fake_sync_runs)
    with TestClient(app) as client:
        response = client.get("/api/v1/sync/runs?limit=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_runs"][0]["job_type"] == "incremental"
    assert payload["data_runs"][0]["quote_count"] == 55
    assert payload["sector_runs"][0]["status"] == "partial"
