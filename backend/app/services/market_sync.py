import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tenacity import retry, stop_after_attempt, wait_exponential

from app.data_sources.base import MarketDataSource, StockRecord
from app.models import DailyQuote, DataSyncRun, Stock, TradingCalendar

logger = logging.getLogger(__name__)
UPSERT_BATCH_SIZE = 1000


@dataclass
class SyncResult:
    run_id: int | None = None
    status: str = "running"
    stocks: int = 0
    quotes: int = 0
    failed_symbols: int = 0
    message: str | None = None


@dataclass
class UniverseSyncResult:
    run_id: int | None = None
    status: str = "completed"
    stocks: int = 0
    quotes: int = 0
    failed_symbols: int = 0
    message: str | None = None


class MarketSyncService:
    def __init__(
        self,
        source: MarketDataSource,
        session_factory: async_sessionmaker[AsyncSession],
        concurrency: int = 4,
        retries: int = 3,
    ):
        self.source = source
        self.session_factory = session_factory
        self.semaphore = asyncio.Semaphore(concurrency)
        self.retries = retries

    async def _upsert(
        self,
        model: type,
        rows: list[dict],
        keys: list[str],
        update_columns: set[str] | None = None,
    ) -> None:
        if not rows:
            return
        async with self.session_factory() as session, session.begin():
            for start in range(0, len(rows), UPSERT_BATCH_SIZE):
                batch = rows[start : start + UPSERT_BATCH_SIZE]
                statement = insert(model).values(batch)
                updates = {
                    column.name: getattr(statement.excluded, column.name)
                    for column in model.__table__.columns
                    if column.name not in keys
                    and column.name != "created_at"
                    and (update_columns is None or column.name in update_columns)
                }
                await session.execute(
                    statement.on_conflict_do_update(index_elements=keys, set_=updates)
                )

    async def _start_run(self, job_type: str, requested_days: int) -> int:
        async with self.session_factory() as session, session.begin():
            run = DataSyncRun(
                job_type=job_type,
                status="running",
                requested_days=requested_days,
            )
            session.add(run)
            await session.flush()
            return run.id

    async def _finish_run(self, result: SyncResult) -> None:
        if result.run_id is None:
            return
        async with self.session_factory() as session, session.begin():
            await session.execute(
                update(DataSyncRun)
                .where(DataSyncRun.id == result.run_id)
                .values(
                    status=result.status,
                    stock_count=result.stocks,
                    quote_count=result.quotes,
                    failed_symbols=result.failed_symbols,
                    message=result.message,
                    finished_at=datetime.now(UTC),
                )
            )

    async def _fetch_stock_list(self) -> list[StockRecord]:
        @retry(
            stop=stop_after_attempt(self.retries),
            wait=wait_exponential(min=1, max=8),
            reraise=True,
        )
        async def fetch():
            return await self.source.fetch_stock_list()

        return await fetch()

    async def _existing_stocks(
        self,
        limit: int | None,
        offset: int = 0,
        *,
        quote_enabled_only: bool = True,
    ) -> list[StockRecord]:
        statement = select(Stock).where(Stock.list_status == "listed")
        if quote_enabled_only:
            statement = statement.where(Stock.quote_enabled.is_(True))
        statement = statement.order_by(Stock.symbol).offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        async with self.session_factory() as session:
            rows = (await session.scalars(statement)).all()
        return [
            StockRecord(symbol=stock.symbol, name=stock.name, exchange=stock.exchange)
            for stock in rows
        ]

    async def sync_stock_universe(self, limit: int | None = None) -> UniverseSyncResult:
        result = UniverseSyncResult(run_id=await self._start_run("universe", 0))
        try:
            stocks = await self._fetch_stock_list()
            if limit is not None:
                stocks = stocks[:limit]
            await self._upsert(
                Stock,
                [
                    {
                        "symbol": stock.symbol,
                        "name": stock.name,
                        "exchange": stock.exchange,
                        "list_status": "listed",
                        "source": self.source.name,
                    }
                    for stock in stocks
                ],
                ["symbol"],
                update_columns={"name", "exchange", "list_status", "source"},
            )
            result.stocks = len(stocks)
            await self._finish_run(result)
            logger.info("stock universe sync complete stocks=%d", len(stocks))
            return result
        except Exception as exc:
            result.status = "error"
            result.message = str(exc)[:512]
            await self._finish_run(result)
            logger.exception("stock universe sync failed run_id=%s", result.run_id)
            raise

    async def sync(
        self,
        days: int = 30,
        limit: int | None = None,
        *,
        job_type: str = "bootstrap",
        use_existing_universe: bool = False,
        require_open_day: bool = False,
        as_of: date | None = None,
        offset: int = 0,
        include_disabled: bool = False,
        enable_synced_stocks: bool = False,
    ) -> SyncResult:
        result = SyncResult(run_id=await self._start_run(job_type, days))
        try:
            end = as_of or date.today()
            calendar_start = end - timedelta(days=max(days * 3, 60))
            trading_days = await self.source.fetch_trading_days(calendar_start, end)
            selected_days = trading_days[-days:]
            if require_open_day and end not in trading_days:
                result.status = "skipped"
                result.message = f"{end.isoformat()} is not an open trading day"
                await self._finish_run(result)
                logger.info("incremental sync skipped reason=%s", result.message)
                return result
            if not selected_days:
                raise RuntimeError("No trading days returned by data source")

            if use_existing_universe:
                stocks = await self._existing_stocks(
                    limit,
                    offset,
                    quote_enabled_only=not include_disabled,
                )
                if not stocks:
                    raise RuntimeError(
                        "Managed stock universe is empty; run sync-market-data first"
                    )
            else:
                stocks = await self._fetch_stock_list()
                if limit is not None:
                    stocks = stocks[:limit]
                await self._upsert(
                    Stock,
                    [
                        {
                            "symbol": stock.symbol,
                            "name": stock.name,
                            "exchange": stock.exchange,
                            "quote_enabled": True,
                            "source": self.source.name,
                        }
                        for stock in stocks
                    ],
                    ["symbol"],
                )

            await self._upsert(
                TradingCalendar,
                [
                    {
                        "trade_date": day,
                        "exchange": "CN",
                        "is_open": True,
                        "source": self.source.name,
                    }
                    for day in selected_days
                ],
                ["trade_date", "exchange"],
            )
            result.stocks = len(stocks)

            async def sync_symbol(symbol: str) -> None:
                async with self.semaphore:
                    try:

                        @retry(
                            stop=stop_after_attempt(self.retries),
                            wait=wait_exponential(min=1, max=8),
                            reraise=True,
                        )
                        async def fetch():
                            return await self.source.fetch_daily_quotes(
                                symbol, selected_days[0], selected_days[-1]
                            )

                        quotes = await fetch()
                        if enable_synced_stocks and not quotes:
                            raise RuntimeError(f"No daily quotes returned for {symbol}")
                        await self._upsert(
                            DailyQuote,
                            [
                                {**quote.__dict__, "source": self.source.name}
                                for quote in quotes
                            ],
                            ["symbol", "trade_date"],
                        )
                        result.quotes += len(quotes)
                        if enable_synced_stocks:
                            async with self.session_factory() as session, session.begin():
                                await session.execute(
                                    update(Stock)
                                    .where(Stock.symbol == symbol)
                                    .values(quote_enabled=True, updated_at=func.now())
                                )
                        logger.info("synced symbol=%s rows=%d", symbol, len(quotes))
                    except Exception:
                        result.failed_symbols += 1
                        logger.exception("failed to sync symbol=%s", symbol)

            await asyncio.gather(*(sync_symbol(stock.symbol) for stock in stocks))
            result.status = "completed" if result.failed_symbols == 0 else "partial"
            if result.failed_symbols:
                result.message = f"{result.failed_symbols} symbols failed"
            await self._finish_run(result)
            logger.info(
                "sync complete run_id=%s status=%s stocks=%d quotes=%d failed_symbols=%d",
                result.run_id,
                result.status,
                result.stocks,
                result.quotes,
                result.failed_symbols,
            )
            return result
        except Exception as exc:
            result.status = "error"
            result.message = str(exc)[:512]
            await self._finish_run(result)
            logger.exception("sync failed run_id=%s", result.run_id)
            raise

    async def sync_incremental(
        self,
        lookback_days: int = 5,
        limit: int | None = None,
        *,
        as_of: date | None = None,
    ) -> SyncResult:
        return await self.sync(
            days=lookback_days,
            limit=limit,
            job_type="incremental",
            use_existing_universe=True,
            require_open_day=True,
            as_of=as_of,
        )

    async def sync_quote_batch(
        self,
        days: int = 30,
        batch_size: int = 100,
        offset: int = 0,
        *,
        as_of: date | None = None,
    ) -> SyncResult:
        return await self.sync(
            days=days,
            limit=batch_size,
            job_type="quote_batch",
            use_existing_universe=True,
            as_of=as_of,
            offset=offset,
            include_disabled=True,
            enable_synced_stocks=True,
        )
