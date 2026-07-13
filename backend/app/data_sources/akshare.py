import asyncio
import logging
from datetime import date
from decimal import Decimal

import akshare as ak
import pandas as pd

from app.data_sources.base import DailyQuoteRecord, MarketDataSource, StockRecord

logger = logging.getLogger(__name__)


def _decimal(value: object) -> Decimal | None:
    if value is None or pd.isna(value):
        return None
    return Decimal(str(value))


def _exchange(symbol: str) -> str:
    if symbol.startswith(("5", "6", "9")):
        return "SSE"
    if symbol.startswith(("4", "8")):
        return "BSE"
    return "SZSE"


def _tencent_symbol(symbol: str) -> str:
    exchange = _exchange(symbol)
    prefix = {"SSE": "sh", "BSE": "bj", "SZSE": "sz"}[exchange]
    return f"{prefix}{symbol}"


class AKShareDataSource(MarketDataSource):
    name = "akshare"

    async def health_check(self) -> None:
        frame = await asyncio.to_thread(ak.stock_info_a_code_name)
        if frame.empty:
            raise RuntimeError("AKShare returned an empty stock list")

    async def fetch_stock_list(self) -> list[StockRecord]:
        frame = await asyncio.to_thread(ak.stock_info_a_code_name)
        return [
            StockRecord(
                symbol=str(row["code"]).zfill(6),
                name=str(row["name"]),
                exchange=_exchange(str(row["code"]).zfill(6)),
            )
            for _, row in frame.iterrows()
        ]

    async def fetch_trading_days(self, start: date, end: date) -> list[date]:
        frame = await asyncio.to_thread(ak.tool_trade_date_hist_sina)
        days = pd.to_datetime(frame["trade_date"]).dt.date
        return sorted(day for day in days if start <= day <= end)

    async def fetch_daily_quotes(
        self, symbol: str, start: date, end: date
    ) -> list[DailyQuoteRecord]:
        try:
            frame = await asyncio.to_thread(
                ak.stock_zh_a_hist,
                symbol=symbol,
                period="daily",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust="",
            )
        except Exception as exc:
            logger.warning(
                "AKShare Eastmoney daily quotes failed; using Tencent fallback "
                "symbol=%s error=%s",
                symbol,
                exc,
            )
            frame = await asyncio.to_thread(
                ak.stock_zh_a_hist_tx,
                symbol=_tencent_symbol(symbol),
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust="",
            )
            return [
                DailyQuoteRecord(
                    symbol=symbol,
                    trade_date=pd.to_datetime(row["date"]).date(),
                    open=_decimal(row["open"]),
                    high=_decimal(row["high"]),
                    low=_decimal(row["low"]),
                    close=_decimal(row["close"]),
                    volume=_decimal(row.get("amount")),
                    amount=None,
                    amplitude=None,
                    pct_change=None,
                    change=None,
                    turnover_rate=None,
                )
                for _, row in frame.iterrows()
            ]
        records: list[DailyQuoteRecord] = []
        for _, row in frame.iterrows():
            records.append(
                DailyQuoteRecord(
                    symbol=symbol,
                    trade_date=pd.to_datetime(row["日期"]).date(),
                    open=_decimal(row["开盘"]),
                    high=_decimal(row["最高"]),
                    low=_decimal(row["最低"]),
                    close=_decimal(row["收盘"]),
                    volume=_decimal(row["成交量"]),
                    amount=_decimal(row.get("成交额")),
                    amplitude=_decimal(row.get("振幅")),
                    pct_change=_decimal(row.get("涨跌幅")),
                    change=_decimal(row.get("涨跌额")),
                    turnover_rate=_decimal(row.get("换手率")),
                )
            )
        return records
