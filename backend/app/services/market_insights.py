from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import and_, case, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import DailyQuote, DataSyncRun, Stock, TradingCalendar


@dataclass(frozen=True)
class DataQualitySnapshot:
    status: str
    latest_trade_date: date | None
    expected_trade_date: date | None
    managed_stocks: int
    quoted_stocks: int
    coverage_pct: float
    invalid_ohlc_rows: int
    nonpositive_volume_rows: int
    missing_amount_rows: int
    amount_coverage_pct: float
    last_sync_status: str | None
    last_sync_finished_at: datetime | None
    message: str


@dataclass(frozen=True)
class MarketOverviewSnapshot:
    as_of: date
    previous_trade_date: date | None
    universe_size: int
    quoted_stocks: int
    comparison_stocks: int
    advancers: int
    decliners: int
    unchanged: int
    advance_decline_ratio: float | None
    average_pct_change: float | None
    total_amount: float | None
    amount_coverage_pct: float
    data_quality_status: str


class MarketInsightsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def data_quality(self, today: date | None = None) -> DataQualitySnapshot:
        effective_today = today or date.today()
        latest_trade_date = await self.session.scalar(select(func.max(DailyQuote.trade_date)))
        expected_trade_date = await self.session.scalar(
            select(func.max(TradingCalendar.trade_date)).where(
                TradingCalendar.is_open.is_(True),
                TradingCalendar.trade_date <= effective_today,
            )
        )
        managed_stocks = int(
            await self.session.scalar(
                select(func.count()).select_from(Stock).where(Stock.list_status == "listed")
            )
            or 0
        )
        last_run = await self.session.scalar(
            select(DataSyncRun).order_by(DataSyncRun.started_at.desc()).limit(1)
        )

        if latest_trade_date is None:
            return DataQualitySnapshot(
                status="error",
                latest_trade_date=None,
                expected_trade_date=expected_trade_date,
                managed_stocks=managed_stocks,
                quoted_stocks=0,
                coverage_pct=0.0,
                invalid_ohlc_rows=0,
                nonpositive_volume_rows=0,
                missing_amount_rows=0,
                amount_coverage_pct=0.0,
                last_sync_status=last_run.status if last_run else None,
                last_sync_finished_at=last_run.finished_at if last_run else None,
                message="No daily quotes are available",
            )

        quoted_stocks = int(
            await self.session.scalar(
                select(func.count(distinct(DailyQuote.symbol))).where(
                    DailyQuote.trade_date == latest_trade_date
                )
            )
            or 0
        )
        invalid_ohlc_rows = int(
            await self.session.scalar(
                select(func.count()).select_from(DailyQuote).where(
                    DailyQuote.trade_date == latest_trade_date,
                    or_(
                        DailyQuote.open <= 0,
                        DailyQuote.high <= 0,
                        DailyQuote.low <= 0,
                        DailyQuote.close <= 0,
                        DailyQuote.high < DailyQuote.low,
                        DailyQuote.high < DailyQuote.open,
                        DailyQuote.high < DailyQuote.close,
                        DailyQuote.low > DailyQuote.open,
                        DailyQuote.low > DailyQuote.close,
                    ),
                )
            )
            or 0
        )
        nonpositive_volume_rows = int(
            await self.session.scalar(
                select(func.count()).select_from(DailyQuote).where(
                    DailyQuote.trade_date == latest_trade_date,
                    DailyQuote.volume <= 0,
                )
            )
            or 0
        )
        missing_amount_rows = int(
            await self.session.scalar(
                select(func.count()).select_from(DailyQuote).where(
                    DailyQuote.trade_date == latest_trade_date,
                    DailyQuote.amount.is_(None),
                )
            )
            or 0
        )
        coverage_pct = round(quoted_stocks / managed_stocks * 100, 2) if managed_stocks else 0.0
        amount_coverage_pct = (
            round((quoted_stocks - missing_amount_rows) / quoted_stocks * 100, 2)
            if quoted_stocks
            else 0.0
        )

        stale = expected_trade_date is not None and latest_trade_date < expected_trade_date
        last_sync_unhealthy = last_run is not None and last_run.status in {"error", "partial"}
        if stale or invalid_ohlc_rows or quoted_stocks == 0:
            status = "error"
            message = "Latest market data is stale or contains invalid OHLC rows"
        elif (
            coverage_pct < 95
            or nonpositive_volume_rows
            or amount_coverage_pct < 95
            or last_sync_unhealthy
        ):
            status = "warning"
            message = "Core prices are usable, but coverage or optional fields are incomplete"
        else:
            status = "ok"
            message = "Latest managed-universe market data passed quality checks"

        return DataQualitySnapshot(
            status=status,
            latest_trade_date=latest_trade_date,
            expected_trade_date=expected_trade_date,
            managed_stocks=managed_stocks,
            quoted_stocks=quoted_stocks,
            coverage_pct=coverage_pct,
            invalid_ohlc_rows=invalid_ohlc_rows,
            nonpositive_volume_rows=nonpositive_volume_rows,
            missing_amount_rows=missing_amount_rows,
            amount_coverage_pct=amount_coverage_pct,
            last_sync_status=last_run.status if last_run else None,
            last_sync_finished_at=last_run.finished_at if last_run else None,
            message=message,
        )

    async def market_overview(self) -> MarketOverviewSnapshot | None:
        latest_trade_date = await self.session.scalar(select(func.max(DailyQuote.trade_date)))
        if latest_trade_date is None:
            return None
        previous_trade_date = await self.session.scalar(
            select(func.max(DailyQuote.trade_date)).where(
                DailyQuote.trade_date < latest_trade_date
            )
        )
        quality = await self.data_quality()
        current = aliased(DailyQuote)
        previous = aliased(DailyQuote)
        join_condition = and_(
            current.symbol == previous.symbol,
            previous.trade_date == previous_trade_date,
        )
        statement = (
            select(
                func.count(current.symbol),
                func.count(previous.symbol),
                func.coalesce(func.sum(case((current.close > previous.close, 1), else_=0)), 0),
                func.coalesce(func.sum(case((current.close < previous.close, 1), else_=0)), 0),
                func.coalesce(func.sum(case((current.close == previous.close, 1), else_=0)), 0),
                func.avg(
                    case(
                        (
                            previous.close > 0,
                            (current.close / previous.close - 1) * 100,
                        )
                    )
                ),
                func.sum(current.amount),
                func.count(current.amount),
            )
            .select_from(current)
            .outerjoin(previous, join_condition)
            .where(current.trade_date == latest_trade_date)
        )
        row = (await self.session.execute(statement)).one()
        quoted_stocks = int(row[0] or 0)
        comparison_stocks = int(row[1] or 0)
        advancers = int(row[2] or 0)
        decliners = int(row[3] or 0)
        unchanged = int(row[4] or 0)
        average_pct_change = round(float(row[5]), 4) if row[5] is not None else None
        total_amount = float(row[6]) if row[6] is not None else None
        amount_coverage_pct = (
            round(int(row[7] or 0) / quoted_stocks * 100, 2) if quoted_stocks else 0.0
        )
        advance_decline_ratio = round(advancers / decliners, 4) if decliners else None
        return MarketOverviewSnapshot(
            as_of=latest_trade_date,
            previous_trade_date=previous_trade_date,
            universe_size=quality.managed_stocks,
            quoted_stocks=quoted_stocks,
            comparison_stocks=comparison_stocks,
            advancers=advancers,
            decliners=decliners,
            unchanged=unchanged,
            advance_decline_ratio=advance_decline_ratio,
            average_pct_change=average_pct_change,
            total_amount=total_amount,
            amount_coverage_pct=amount_coverage_pct,
            data_quality_status=quality.status,
        )
