import asyncio
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tenacity import retry, stop_after_attempt, wait_exponential

from app.data_sources.base import MarketDataSource
from app.models import DailyQuote, Stock, TradingCalendar

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    stocks: int = 0
    quotes: int = 0
    failed_symbols: int = 0


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

    async def _upsert(self, model: type, rows: list[dict], keys: list[str]) -> None:
        if not rows:
            return
        async with self.session_factory() as session, session.begin():
            statement = insert(model).values(rows)
            updates = {
                c.name: getattr(statement.excluded, c.name)
                for c in model.__table__.columns
                if c.name not in keys and c.name != "created_at"
            }
            await session.execute(
                statement.on_conflict_do_update(index_elements=keys, set_=updates)
            )

    async def sync(self, days: int = 30, limit: int | None = None) -> SyncResult:
        stocks = await self.source.fetch_stock_list()
        if limit is not None:
            stocks = stocks[:limit]
        await self._upsert(
            Stock,
            [
                {
                    "symbol": x.symbol,
                    "name": x.name,
                    "exchange": x.exchange,
                    "source": self.source.name,
                }
                for x in stocks
            ],
            ["symbol"],
        )
        end = date.today()
        calendar_start = end - timedelta(days=max(days * 2, 60))
        trading_days = await self.source.fetch_trading_days(calendar_start, end)
        selected_days = trading_days[-days:]
        if not selected_days:
            raise RuntimeError("No trading days returned by data source")
        await self._upsert(
            TradingCalendar,
            [
                {"trade_date": day, "exchange": "CN", "is_open": True, "source": self.source.name}
                for day in selected_days
            ],
            ["trade_date", "exchange"],
        )
        result = SyncResult(stocks=len(stocks))

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
                    await self._upsert(
                        DailyQuote,
                        [{**q.__dict__, "source": self.source.name} for q in quotes],
                        ["symbol", "trade_date"],
                    )
                    result.quotes += len(quotes)
                    logger.info("synced symbol=%s rows=%d", symbol, len(quotes))
                except Exception:
                    result.failed_symbols += 1
                    logger.exception("failed to sync symbol=%s", symbol)

        await asyncio.gather(*(sync_symbol(stock.symbol) for stock in stocks))
        logger.info(
            "sync complete stocks=%d quotes=%d failed_symbols=%d",
            result.stocks,
            result.quotes,
            result.failed_symbols,
        )
        return result
