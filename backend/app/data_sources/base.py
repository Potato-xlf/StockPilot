from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class StockRecord:
    symbol: str
    name: str
    exchange: str


@dataclass(frozen=True)
class DailyQuoteRecord:
    symbol: str
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    amount: Decimal | None = None
    amplitude: Decimal | None = None
    pct_change: Decimal | None = None
    change: Decimal | None = None
    turnover_rate: Decimal | None = None


@dataclass(frozen=True)
class SectorRecord:
    code: str
    name: str
    sector_type: str
    latest_price: Decimal | None = None
    pct_change: Decimal | None = None
    turnover_rate: Decimal | None = None
    total_market_cap: Decimal | None = None
    advancers: int | None = None
    decliners: int | None = None
    leading_stock: str | None = None
    leading_stock_pct: Decimal | None = None


@dataclass(frozen=True)
class SectorMemberRecord:
    symbol: str
    name: str
    exchange: str


class MarketDataSource(ABC):
    name: str

    @abstractmethod
    async def health_check(self) -> None: ...

    @abstractmethod
    async def fetch_stock_list(self) -> list[StockRecord]: ...

    @abstractmethod
    async def fetch_trading_days(self, start: date, end: date) -> list[date]: ...

    @abstractmethod
    async def fetch_daily_quotes(
        self, symbol: str, start: date, end: date
    ) -> list[DailyQuoteRecord]: ...

    @abstractmethod
    async def fetch_sectors(self, sector_type: str) -> list[SectorRecord]: ...

    @abstractmethod
    async def fetch_sector_members(
        self, sector_code: str, sector_type: str
    ) -> list[SectorMemberRecord]: ...
