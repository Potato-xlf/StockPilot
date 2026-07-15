import os
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from app.data_sources.base import (
    DailyQuoteRecord,
    MarketDataSource,
    SectorMemberRecord,
    SectorRecord,
    StockRecord,
)
from app.db.base import Base
from app.models import (
    DailyQuote,
    DataSyncRun,
    Sector,
    SectorMember,
    SectorSnapshot,
    SectorSyncRun,
    Stock,
    TradingCalendar,
)
from app.services.market_insights import MarketInsightsService
from app.services.market_sync import MarketSyncService
from app.services.sector_sync import SectorSyncService
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
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
        self.sector_list_calls = 0

    async def health_check(self) -> None:
        return None

    async def fetch_stock_list(self) -> list[StockRecord]:
        self.stock_list_calls += 1
        return [
            StockRecord(symbol="000001", name="平安银行", exchange="SZSE"),
            StockRecord(symbol="000002", name="万科A", exchange="SZSE"),
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

    async def fetch_sectors(self, sector_type: str) -> list[SectorRecord]:
        self.sector_list_calls += 1
        first_pct, second_pct = (
            (Decimal("1.0"), Decimal("2.0"))
            if self.sector_list_calls == 1
            else (Decimal("3.0"), Decimal("1.0"))
        )
        return [
            SectorRecord(
                code="BK0001",
                name="银行",
                sector_type=sector_type,
                pct_change=first_pct,
                turnover_rate=Decimal("1.2"),
                advancers=2,
                decliners=1,
                leading_stock="平安银行",
                leading_stock_pct=Decimal("4.0"),
            ),
            SectorRecord(
                code="BK0002",
                name="地产",
                sector_type=sector_type,
                pct_change=second_pct,
                turnover_rate=Decimal("0.9"),
                advancers=1,
                decliners=2,
                leading_stock="万科A",
                leading_stock_pct=Decimal("3.0"),
            ),
        ]

    async def fetch_sector_members(
        self, sector_code: str, sector_type: str
    ) -> list[SectorMemberRecord]:
        if sector_code == "BK0001":
            return [
                SectorMemberRecord("000001", "平安银行", "SZSE"),
                SectorMemberRecord("600000", "浦发银行", "SSE"),
            ]
        return [SectorMemberRecord("000002", "万科A", "SZSE")]


@pytest.mark.asyncio
async def test_market_sync_is_idempotent() -> None:
    database_url = os.environ["DATABASE_URL"]
    database_name = make_url(database_url).database or ""
    if not database_name.endswith("_test"):
        pytest.fail(
            "integration tests require a dedicated database whose name ends with _test"
        )
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    source = FakeMarketDataSource()
    service = MarketSyncService(source, session_factory, concurrency=2)
    first = await service.sync(days=2, limit=2)
    second = await service.sync(days=2, limit=2)
    incremental = await service.sync_incremental(
        lookback_days=2, as_of=date(2026, 7, 10)
    )
    skipped = await service.sync_incremental(
        lookback_days=2, as_of=date(2026, 7, 11)
    )
    universe = await service.sync_stock_universe()
    batch = await service.sync_quote_batch(
        days=2, batch_size=1, offset=2, as_of=date(2026, 7, 10)
    )
    sector_service = SectorSyncService(source, session_factory, concurrency=2)
    first_sectors = await sector_service.sync("industry", date(2026, 7, 9))
    second_sectors = await sector_service.sync("industry", date(2026, 7, 10))

    assert first.quotes == second.quotes == 4
    assert first.failed_symbols == second.failed_symbols == 0
    assert incremental.status == "completed"
    assert incremental.quotes == 4
    assert skipped.status == "skipped"
    assert universe.stocks == 3
    assert batch.status == "completed" and batch.quotes == 2
    assert first_sectors.members == second_sectors.members == 3
    assert source.stock_list_calls == 3

    async with session_factory() as session:
        stock_count = await session.scalar(select(func.count()).select_from(Stock))
        calendar_count = await session.scalar(select(func.count()).select_from(TradingCalendar))
        quote_count = await session.scalar(select(func.count()).select_from(DailyQuote))
        run_count = await session.scalar(select(func.count()).select_from(DataSyncRun))
        sector_count = await session.scalar(select(func.count()).select_from(Sector))
        member_count = await session.scalar(select(func.count()).select_from(SectorMember))
        snapshot_count = await session.scalar(
            select(func.count()).select_from(SectorSnapshot)
        )
        sector_run_count = await session.scalar(
            select(func.count()).select_from(SectorSyncRun)
        )
        enabled_count = await session.scalar(
            select(func.count()).select_from(Stock).where(Stock.quote_enabled.is_(True))
        )
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
        ranking = await MarketInsightsService(session).sector_ranking("industry")

    assert stock_count == 3
    assert calendar_count == 2
    assert quote_count == 6
    assert run_count == 6
    assert latest_run is not None and latest_run.status == "completed"
    assert enabled_count == 3
    assert sector_count == 2
    assert member_count == 3
    assert snapshot_count == 4
    assert sector_run_count == 2
    assert quality.status == "ok"
    assert quality.coverage_pct == 100.0
    assert intraday_quality.expected_trade_date == date(2026, 7, 9)
    assert intraday_quality.status == "ok"
    assert overview is not None
    assert overview.quoted_stocks == 3
    assert overview.unchanged == 3
    assert overview.data_quality_status == "ok"
    assert ranking is not None
    assert ranking.total_sectors == 2
    assert ranking.items[0].code == "BK0001"
    assert ranking.items[0].previous_rank == 2
    assert ranking.items[0].rank_change == 1
    await engine.dispose()
