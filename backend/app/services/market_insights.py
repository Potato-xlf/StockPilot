from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

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

MARKET_TIMEZONE = ZoneInfo("Asia/Shanghai")
DAILY_DATA_READY_TIME = time(15, 30)


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


@dataclass(frozen=True)
class SectorRankingItemSnapshot:
    rank: int
    previous_rank: int | None
    rank_change: int | None
    code: str
    name: str
    score: float
    pct_change: float | None
    turnover_rate: float | None
    breadth_pct: float | None
    advancers: int | None
    decliners: int | None
    leading_stock: str | None
    leading_stock_pct: float | None
    member_count: int


@dataclass(frozen=True)
class SectorRankingSnapshot:
    as_of: date
    previous_trade_date: date | None
    sector_type: str
    total_sectors: int
    items: list[SectorRankingItemSnapshot]


@dataclass(frozen=True)
class UniverseStatusSnapshot:
    total_listed_stocks: int
    quote_enabled_stocks: int
    pending_quote_stocks: int
    exchange_counts: dict[str, int]
    last_universe_sync_status: str | None
    last_universe_sync_finished_at: datetime | None
    last_quote_batch_status: str | None
    last_quote_batch_finished_at: datetime | None


@dataclass(frozen=True)
class DataSyncRunSnapshot:
    id: int
    job_type: str
    status: str
    requested_days: int
    stock_count: int
    quote_count: int
    failed_symbols: int
    message: str | None
    started_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True)
class SectorSyncRunSnapshot:
    id: int
    sector_type: str
    status: str
    sector_count: int
    member_count: int
    failed_sectors: int
    message: str | None
    started_at: datetime
    finished_at: datetime | None


def _percentile(value: float | None, values: list[float]) -> float:
    if value is None or not values:
        return 0.0
    less = sum(item < value for item in values)
    equal = sum(item == value for item in values)
    return (less + equal / 2) / len(values) * 100


def _rank_sector_rows(rows: list[dict]) -> list[dict]:
    pct_values = [row["pct_change"] for row in rows if row["pct_change"] is not None]
    turnover_values = [
        row["turnover_rate"] for row in rows if row["turnover_rate"] is not None
    ]
    breadth_values = [row["breadth_pct"] for row in rows if row["breadth_pct"] is not None]
    leader_values = [
        row["leading_stock_pct"]
        for row in rows
        if row["leading_stock_pct"] is not None
    ]
    ranked = []
    for row in rows:
        score = (
            _percentile(row["pct_change"], pct_values) * 0.50
            + _percentile(row["breadth_pct"], breadth_values) * 0.25
            + _percentile(row["turnover_rate"], turnover_values) * 0.15
            + _percentile(row["leading_stock_pct"], leader_values) * 0.10
        )
        ranked.append({**row, "score": round(score, 2)})
    return sorted(
        ranked,
        key=lambda row: (
            row["score"],
            row["pct_change"]
            if row["pct_change"] is not None
            else float("-inf"),
        ),
        reverse=True,
    )


class MarketInsightsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def sync_runs(
        self, limit: int = 20
    ) -> tuple[list[DataSyncRunSnapshot], list[SectorSyncRunSnapshot]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        data_rows = (
            await self.session.scalars(
                select(DataSyncRun)
                .order_by(DataSyncRun.started_at.desc(), DataSyncRun.id.desc())
                .limit(limit)
            )
        ).all()
        sector_rows = (
            await self.session.scalars(
                select(SectorSyncRun)
                .order_by(SectorSyncRun.started_at.desc(), SectorSyncRun.id.desc())
                .limit(limit)
            )
        ).all()
        return (
            [
                DataSyncRunSnapshot(
                    id=row.id,
                    job_type=row.job_type,
                    status=row.status,
                    requested_days=row.requested_days,
                    stock_count=row.stock_count,
                    quote_count=row.quote_count,
                    failed_symbols=row.failed_symbols,
                    message=row.message,
                    started_at=row.started_at,
                    finished_at=row.finished_at,
                )
                for row in data_rows
            ],
            [
                SectorSyncRunSnapshot(
                    id=row.id,
                    sector_type=row.sector_type,
                    status=row.status,
                    sector_count=row.sector_count,
                    member_count=row.member_count,
                    failed_sectors=row.failed_sectors,
                    message=row.message,
                    started_at=row.started_at,
                    finished_at=row.finished_at,
                )
                for row in sector_rows
            ],
        )

    async def data_quality(self, now: datetime | None = None) -> DataQualitySnapshot:
        market_now = now or datetime.now(MARKET_TIMEZONE)
        if market_now.tzinfo is None:
            market_now = market_now.replace(tzinfo=MARKET_TIMEZONE)
        else:
            market_now = market_now.astimezone(MARKET_TIMEZONE)
        effective_today = market_now.date()
        latest_trade_date = await self.session.scalar(
            select(func.max(DailyQuote.trade_date))
            .join(Stock, Stock.symbol == DailyQuote.symbol)
            .where(Stock.quote_enabled.is_(True))
        )
        expected_trade_date = await self.session.scalar(
            select(func.max(TradingCalendar.trade_date)).where(
                TradingCalendar.is_open.is_(True),
                TradingCalendar.trade_date <= effective_today,
            )
        )
        if (
            expected_trade_date == effective_today
            and market_now.time().replace(tzinfo=None) < DAILY_DATA_READY_TIME
        ):
            expected_trade_date = await self.session.scalar(
                select(func.max(TradingCalendar.trade_date)).where(
                    TradingCalendar.is_open.is_(True),
                    TradingCalendar.trade_date < effective_today,
                )
            )
        managed_stocks = int(
            await self.session.scalar(
                select(func.count()).select_from(Stock).where(Stock.list_status == "listed")
                .where(Stock.quote_enabled.is_(True))
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
                ).join(Stock, Stock.symbol == DailyQuote.symbol)
                .where(Stock.quote_enabled.is_(True))
            )
            or 0
        )
        invalid_ohlc_rows = int(
            await self.session.scalar(
                select(func.count()).select_from(DailyQuote)
                .join(Stock, Stock.symbol == DailyQuote.symbol)
                .where(
                    DailyQuote.trade_date == latest_trade_date,
                    Stock.quote_enabled.is_(True),
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
                select(func.count()).select_from(DailyQuote)
                .join(Stock, Stock.symbol == DailyQuote.symbol)
                .where(
                    DailyQuote.trade_date == latest_trade_date,
                    Stock.quote_enabled.is_(True),
                    DailyQuote.volume <= 0,
                )
            )
            or 0
        )
        missing_amount_rows = int(
            await self.session.scalar(
                select(func.count()).select_from(DailyQuote)
                .join(Stock, Stock.symbol == DailyQuote.symbol)
                .where(
                    DailyQuote.trade_date == latest_trade_date,
                    Stock.quote_enabled.is_(True),
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

    async def universe_status(self) -> UniverseStatusSnapshot:
        total_listed = int(
            await self.session.scalar(
                select(func.count()).select_from(Stock).where(Stock.list_status == "listed")
            )
            or 0
        )
        quote_enabled = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Stock)
                .where(
                    Stock.list_status == "listed",
                    Stock.quote_enabled.is_(True),
                )
            )
            or 0
        )
        exchange_counts = {
            exchange: int(count)
            for exchange, count in await self.session.execute(
                select(Stock.exchange, func.count())
                .where(Stock.list_status == "listed")
                .group_by(Stock.exchange)
                .order_by(Stock.exchange)
            )
        }
        last_universe = await self.session.scalar(
            select(DataSyncRun)
            .where(DataSyncRun.job_type == "universe")
            .order_by(DataSyncRun.started_at.desc())
            .limit(1)
        )
        last_batch = await self.session.scalar(
            select(DataSyncRun)
            .where(DataSyncRun.job_type == "quote_batch")
            .order_by(DataSyncRun.started_at.desc())
            .limit(1)
        )
        return UniverseStatusSnapshot(
            total_listed_stocks=total_listed,
            quote_enabled_stocks=quote_enabled,
            pending_quote_stocks=max(total_listed - quote_enabled, 0),
            exchange_counts=exchange_counts,
            last_universe_sync_status=last_universe.status if last_universe else None,
            last_universe_sync_finished_at=(
                last_universe.finished_at if last_universe else None
            ),
            last_quote_batch_status=last_batch.status if last_batch else None,
            last_quote_batch_finished_at=last_batch.finished_at if last_batch else None,
        )

    async def market_overview(self) -> MarketOverviewSnapshot | None:
        latest_trade_date = await self.session.scalar(
            select(func.max(DailyQuote.trade_date))
            .join(Stock, Stock.symbol == DailyQuote.symbol)
            .where(Stock.quote_enabled.is_(True))
        )
        if latest_trade_date is None:
            return None
        previous_trade_date = await self.session.scalar(
            select(func.max(DailyQuote.trade_date))
            .join(Stock, Stock.symbol == DailyQuote.symbol)
            .where(
                DailyQuote.trade_date < latest_trade_date,
                Stock.quote_enabled.is_(True),
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
            .join(Stock, Stock.symbol == current.symbol)
            .outerjoin(previous, join_condition)
            .where(
                current.trade_date == latest_trade_date,
                Stock.quote_enabled.is_(True),
            )
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

    async def sector_ranking(
        self, sector_type: str, limit: int = 20
    ) -> SectorRankingSnapshot | None:
        if sector_type not in {"industry", "concept"}:
            raise ValueError("sector_type must be industry or concept")
        latest_date = await self.session.scalar(
            select(func.max(SectorSnapshot.trade_date)).where(
                SectorSnapshot.sector_type == sector_type
            )
        )
        if latest_date is None:
            return None
        previous_date = await self.session.scalar(
            select(func.max(SectorSnapshot.trade_date)).where(
                SectorSnapshot.sector_type == sector_type,
                SectorSnapshot.trade_date < latest_date,
            )
        )
        member_counts = (
            select(
                SectorMember.sector_type,
                SectorMember.sector_code,
                func.count().label("member_count"),
            )
            .group_by(SectorMember.sector_type, SectorMember.sector_code)
            .subquery()
        )

        async def fetch_rows(trade_date: date) -> list[dict]:
            statement = (
                select(
                    SectorSnapshot,
                    Sector.name,
                    func.coalesce(member_counts.c.member_count, 0),
                )
                .join(
                    Sector,
                    and_(
                        Sector.sector_type == SectorSnapshot.sector_type,
                        Sector.code == SectorSnapshot.sector_code,
                    ),
                )
                .outerjoin(
                    member_counts,
                    and_(
                        member_counts.c.sector_type == SectorSnapshot.sector_type,
                        member_counts.c.sector_code == SectorSnapshot.sector_code,
                    ),
                )
                .where(
                    SectorSnapshot.sector_type == sector_type,
                    SectorSnapshot.trade_date == trade_date,
                )
            )
            result = []
            for snapshot, name, member_count in await self.session.execute(statement):
                advancers = snapshot.advancers
                decliners = snapshot.decliners
                breadth_pct = None
                if advancers is not None and decliners is not None and advancers + decliners:
                    breadth_pct = round(advancers / (advancers + decliners) * 100, 2)
                result.append(
                    {
                        "code": snapshot.sector_code,
                        "name": name,
                        "pct_change": (
                            float(snapshot.pct_change)
                            if snapshot.pct_change is not None
                            else None
                        ),
                        "turnover_rate": (
                            float(snapshot.turnover_rate)
                            if snapshot.turnover_rate is not None
                            else None
                        ),
                        "breadth_pct": breadth_pct,
                        "advancers": advancers,
                        "decliners": decliners,
                        "leading_stock": snapshot.leading_stock,
                        "leading_stock_pct": (
                            float(snapshot.leading_stock_pct)
                            if snapshot.leading_stock_pct is not None
                            else None
                        ),
                        "member_count": int(member_count),
                    }
                )
            return result

        ranked = _rank_sector_rows(await fetch_rows(latest_date))
        previous_ranks: dict[str, int] = {}
        if previous_date is not None:
            previous_ranked = _rank_sector_rows(await fetch_rows(previous_date))
            previous_ranks = {
                row["code"]: rank for rank, row in enumerate(previous_ranked, start=1)
            }

        items = []
        for rank, row in enumerate(ranked[:limit], start=1):
            previous_rank = previous_ranks.get(row["code"])
            items.append(
                SectorRankingItemSnapshot(
                    rank=rank,
                    previous_rank=previous_rank,
                    rank_change=(previous_rank - rank if previous_rank is not None else None),
                    **row,
                )
            )
        return SectorRankingSnapshot(
            as_of=latest_date,
            previous_trade_date=previous_date,
            sector_type=sector_type,
            total_sectors=len(ranked),
            items=items,
        )
