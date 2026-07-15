from datetime import date

from app.main import app
from app.services.market_insights import (
    DailyQuoteSnapshot,
    StockQuotesSnapshot,
    StockSnapshot,
)
from fastapi.testclient import TestClient


def test_stocks_query(monkeypatch):
    async def fake_stocks(_self, **kwargs):
        assert kwargs["query"] == "平安"
        assert kwargs["limit"] == 2
        return [StockSnapshot("000001", "平安银行", "SZSE", "listed", True)], 1

    monkeypatch.setattr("app.api.v1.router.MarketInsightsService.stocks", fake_stocks)
    with TestClient(app) as client:
        response = client.get("/api/v1/stocks?q=平安&limit=2")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["symbol"] == "000001"


def test_stock_quotes_query(monkeypatch):
    async def fake_quotes(_self, symbol, limit):
        assert symbol == "000001"
        assert limit == 5
        return StockQuotesSnapshot(
            symbol="000001",
            name="平安银行",
            items=[
                DailyQuoteSnapshot(
                    trade_date=date(2026, 7, 14),
                    open=10.0,
                    high=10.5,
                    low=9.9,
                    close=10.2,
                    volume=1000.0,
                    amount=10200.0,
                    amplitude=6.0,
                    pct_change=2.0,
                    change=0.2,
                    turnover_rate=1.2,
                )
            ],
        )

    monkeypatch.setattr("app.api.v1.router.MarketInsightsService.stock_quotes", fake_quotes)
    with TestClient(app) as client:
        response = client.get("/api/v1/stocks/000001/quotes?limit=5")

    assert response.status_code == 200
    assert response.json()["name"] == "平安银行"
    assert response.json()["items"][0]["close"] == 10.2


def test_stock_quotes_rejects_invalid_symbol():
    with TestClient(app) as client:
        response = client.get("/api/v1/stocks/123/quotes")
    assert response.status_code == 422
