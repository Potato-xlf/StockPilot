from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Stock(Base):
    __tablename__ = "stocks"

    symbol: Mapped[str] = mapped_column(String(6), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    list_status: Mapped[str] = mapped_column(String(16), nullable=False, default="listed")
    quote_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="akshare")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TradingCalendar(Base):
    __tablename__ = "trading_calendars"

    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    exchange: Mapped[str] = mapped_column(String(8), primary_key=True, default="CN")
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="akshare")


class DailyQuote(Base):
    __tablename__ = "daily_quotes"
    __table_args__ = (Index("ix_daily_quotes_trade_date", "trade_date"),)

    symbol: Mapped[str] = mapped_column(
        String(6), ForeignKey("stocks.symbol", ondelete="CASCADE"), primary_key=True
    )
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(24, 2), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    amplitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    pct_change: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    change: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    turnover_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="akshare")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DataSyncRun(Base):
    __tablename__ = "data_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    requested_days: Mapped[int] = mapped_column(Integer, nullable=False)
    stock_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quote_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_symbols: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(String(512))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Sector(Base):
    __tablename__ = "sectors"

    sector_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="akshare")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SectorMember(Base):
    __tablename__ = "sector_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["sector_type", "sector_code"],
            ["sectors.sector_type", "sectors.code"],
            ondelete="CASCADE",
        ),
        Index("ix_sector_members_symbol", "symbol"),
    )

    sector_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    sector_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    symbol: Mapped[str] = mapped_column(
        String(6), ForeignKey("stocks.symbol", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="akshare")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SectorSnapshot(Base):
    __tablename__ = "sector_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["sector_type", "sector_code"],
            ["sectors.sector_type", "sectors.code"],
            ondelete="CASCADE",
        ),
        Index("ix_sector_snapshots_trade_date", "trade_date"),
    )

    sector_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    sector_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    latest_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    pct_change: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    turnover_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    total_market_cap: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    advancers: Mapped[int | None] = mapped_column(Integer)
    decliners: Mapped[int | None] = mapped_column(Integer)
    leading_stock: Mapped[str | None] = mapped_column(String(64))
    leading_stock_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="akshare")
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SectorSyncRun(Base):
    __tablename__ = "sector_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sector_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    sector_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_sectors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(String(512))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
