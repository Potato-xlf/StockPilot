import asyncio
import logging
from datetime import date
from decimal import Decimal

import akshare as ak
import pandas as pd

from app.data_sources.base import (
    DailyQuoteRecord,
    MarketDataSource,
    SectorMemberRecord,
    SectorRecord,
    StockRecord,
)

logger = logging.getLogger(__name__)


def _decimal(value: object) -> Decimal | None:
    if value is None or pd.isna(value):
        return None
    return Decimal(str(value))


def _exchange(symbol: str) -> str:
    if symbol.startswith(("4", "8", "92")):
        return "BSE"
    if symbol.startswith(("5", "6", "9")):
        return "SSE"
    return "SZSE"


def _tencent_symbol(symbol: str) -> str:
    exchange = _exchange(symbol)
    prefix = {"SSE": "sh", "BSE": "bj", "SZSE": "sz"}[exchange]
    return f"{prefix}{symbol}"


def _optional_int(value: object) -> int | None:
    decimal_value = _decimal(value)
    return int(decimal_value) if decimal_value is not None else None


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

    async def fetch_sectors(self, sector_type: str) -> list[SectorRecord]:
        if sector_type == "industry":
            frame = await asyncio.to_thread(ak.stock_board_industry_name_em)
        elif sector_type == "concept":
            frame = await asyncio.to_thread(ak.stock_board_concept_name_em)
        else:
            raise ValueError(f"Unsupported sector type: {sector_type}")
        return [
            SectorRecord(
                code=str(row["板块代码"]),
                name=str(row["板块名称"]),
                sector_type=sector_type,
                latest_price=_decimal(row.get("最新价")),
                pct_change=_decimal(row.get("涨跌幅")),
                turnover_rate=_decimal(row.get("换手率")),
                total_market_cap=_decimal(row.get("总市值")),
                advancers=_optional_int(row.get("上涨家数")),
                decliners=_optional_int(row.get("下跌家数")),
                leading_stock=(
                    str(row["领涨股票"])
                    if not pd.isna(row.get("领涨股票"))
                    else None
                ),
                leading_stock_pct=_decimal(row.get("领涨股票-涨跌幅")),
            )
            for _, row in frame.iterrows()
        ]

    async def fetch_sector_members(
        self, sector_code: str, sector_type: str
    ) -> list[SectorMemberRecord]:
        if sector_type == "industry":
            frame = await asyncio.to_thread(
                ak.stock_board_industry_cons_em, symbol=sector_code
            )
        elif sector_type == "concept":
            frame = await asyncio.to_thread(
                ak.stock_board_concept_cons_em, symbol=sector_code
            )
        else:
            raise ValueError(f"Unsupported sector type: {sector_type}")
        return [
            SectorMemberRecord(
                symbol=str(row["代码"]).zfill(6),
                name=str(row["名称"]),
                exchange=_exchange(str(row["代码"]).zfill(6)),
            )
            for _, row in frame.iterrows()
        ]
