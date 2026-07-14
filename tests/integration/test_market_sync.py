import os
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from app.data_sources.base import DailyQuoteRecord, MarketDataSource, StockRecord
from app.db.base import Base
from app.models import DailyQuote, DataSyncRun, Stock, TradingCalendar
from app.services.market_insights import MarketInsightsService
from app.services.market_sync import MarketSyncService
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 to run PostgreSQL integration tests",
    ),
]


class FakeMarketDataSource(MarketDataSource):
    name = "fake"

    def __init__(self) -> None:
        self.stock_list_calls = 0

    async def health_check(self) -> None:
        return None

    async def fetch_stock_list(self) -> list[StockRecord]:
        self.stock_list_calls += 1
        return [
            StockRecord(symbol="000001", name="平安银行", exchange="SZSE"),
            StockRecord(symbol="600000", name="浦发银行", exchange="SSE"),
        ]

    async def fetch_trading_days(self, start: date, end: date) -> list[date]:
        return [date(2026, 7, 9), date(2026, 7, 10)]

    async def fetch_daily_quotes(
        self, symbol: str, start: date, end: date
    ) -> list[DailyQuoteRecord]:
        return [
            DailyQuoteRecord(
                symbol=symbol,
                trade_date=trade_date,
                open=Decimal("10.00"),
                high=Decimal("10.50"),
                low=Decimal("9.80"),
                close=Decimal("10.20"),
                volume=Decimal("100000"),
                amount=Decimal("1020000"),
            )
            for trade_date in (date(2026, 7, 9), date(2026, 7, 10))
        ]


@pytest.mark.asyncio
async def test_market_sync_is_idempotent() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    source = FakeMarketDataSource()
    service = MarketSyncService(source, session_factory, concurrency=2)
    first = await service.sync(days=2)
    second = await service.sync(days=2)
    incremental = await service.sync_incremental(
        lookback_days=2, as_of=date(2026, 7, 10)
    )
    skipped = await service.sync_incremental(
        lookback_days=2, as_of=date(2026, 7, 11)
    )

    assert first.quotes == second.quotes == 4
    assert first.failed_symbols == second.failed_symbols == 0
    assert incremental.status == "completed"
    assert incremental.quotes == 4
    assert skipped.status == "skipped"
    assert source.stock_list_calls == 2

    async with session_factory() as session:
        stock_count = await session.scalar(select(func.count()).select_from(Stock))
        calendar_count = await session.scalar(select(func.count()).select_from(TradingCalendar))
        quote_count = await session.scalar(select(func.count()).select_from(DailyQuote))
        run_count = await session.scalar(select(func.count()).select_from(DataSyncRun))
        latest_run = await session.scalar(
            select(DataSyncRun).order_by(DataSyncRun.id.desc()).limit(1)
        )
        quality = await MarketInsightsService(session).data_quality(
            now=datetime(2026, 7, 10, 18, tzinfo=ZoneInfo("Asia/Shanghai"))
        )
        intraday_quality = await MarketInsightsService(session).data_quality(
            now=datetime(2026, 7, 10, 13, tzinfo=ZoneInfo("Asia/Shanghai"))
        )
        overview = await MarketInsightsService(session).market_overview()

    assert stock_count == 2
    assert calendar_count == 2
    assert quote_count == 4
    assert run_count == 4
    assert latest_run is not None and latest_run.status == "skipped"
    assert quality.status == "ok"
    assert quality.coverage_pct == 100.0
    assert intraday_quality.expected_trade_date == date(2026, 7, 9)
    assert intraday_quality.status == "ok"
    assert overview is not None
    assert overview.quoted_stocks == 2
    assert overview.unchanged == 2
    assert overview.data_quality_status == "ok"
    await engine.dispose()
