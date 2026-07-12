from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Stock(Base):
    __tablename__ = "stocks"

    symbol: Mapped[str] = mapped_column(String(6), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    list_status: Mapped[str] = mapped_column(String(16), nullable=False, default="listed")
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
