from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from app.data_sources.akshare import AKShareDataSource


@pytest.mark.asyncio
async def test_stock_list_mapping(monkeypatch):
    monkeypatch.setattr(
        "app.data_sources.akshare.ak.stock_info_a_code_name",
        lambda: pd.DataFrame(
            [
                {"code": "600000", "name": "浦发银行"},
                {"code": "000001", "name": "平安银行"},
                {"code": "920971", "name": "天马新材"},
            ]
        ),
    )
    stocks = await AKShareDataSource().fetch_stock_list()
    assert [(x.symbol, x.exchange) for x in stocks] == [
        ("600000", "SSE"),
        ("000001", "SZSE"),
        ("920971", "BSE"),
    ]


@pytest.mark.asyncio
async def test_daily_quotes_fall_back_to_tencent(monkeypatch):
    def fail_eastmoney(**_kwargs):
        raise ConnectionError("upstream reset")

    captured = {}

    def tencent_quotes(**kwargs):
        captured.update(kwargs)
        return pd.DataFrame(
            [
                {
                    "date": date(2026, 7, 10),
                    "open": 10.5,
                    "close": 10.45,
                    "high": 10.51,
                    "low": 10.4,
                    "amount": 957320.0,
                }
            ]
        )

    monkeypatch.setattr("app.data_sources.akshare.ak.stock_zh_a_hist", fail_eastmoney)
    monkeypatch.setattr("app.data_sources.akshare.ak.stock_zh_a_hist_tx", tencent_quotes)

    quotes = await AKShareDataSource().fetch_daily_quotes(
        "000001", date(2026, 7, 1), date(2026, 7, 13)
    )

    assert captured["symbol"] == "sz000001"
    assert len(quotes) == 1
    assert quotes[0].trade_date == date(2026, 7, 10)
    assert quotes[0].close == Decimal("10.45")
    assert quotes[0].volume == Decimal("957320.0")
    assert quotes[0].amount is None


@pytest.mark.asyncio
async def test_sector_and_member_mapping(monkeypatch):
    monkeypatch.setattr(
        "app.data_sources.akshare.ak.stock_board_industry_name_em",
        lambda: pd.DataFrame(
            [
                {
                    "板块代码": "BK0475",
                    "板块名称": "银行",
                    "最新价": 1234.5,
                    "涨跌幅": 1.2,
                    "换手率": 0.8,
                    "总市值": 100000,
                    "上涨家数": 30,
                    "下跌家数": 10,
                    "领涨股票": "平安银行",
                    "领涨股票-涨跌幅": 4.5,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        "app.data_sources.akshare.ak.stock_board_industry_cons_em",
        lambda symbol: pd.DataFrame([{"代码": "000001", "名称": "平安银行"}]),
    )

    source = AKShareDataSource()
    sectors = await source.fetch_sectors("industry")
    members = await source.fetch_sector_members("BK0475", "industry")

    assert sectors[0].code == "BK0475"
    assert sectors[0].pct_change == Decimal("1.2")
    assert sectors[0].advancers == 30
    assert members[0].symbol == "000001"
    assert members[0].exchange == "SZSE"


@pytest.mark.asyncio
async def test_industry_sectors_fall_back_to_ths(monkeypatch):
    def fail_eastmoney():
        raise ConnectionError("upstream closed connection")

    monkeypatch.setattr(
        "app.data_sources.akshare.ak.stock_board_industry_name_em", fail_eastmoney
    )
    monkeypatch.setattr(
        "app.data_sources.akshare.ak.stock_board_industry_name_ths",
        lambda: pd.DataFrame([{"name": "银行", "code": "881155"}]),
    )
    monkeypatch.setattr(
        "app.data_sources.akshare.ak.stock_board_industry_summary_ths",
        lambda: pd.DataFrame(
            [
                {
                    "板块": "银行",
                    "涨跌幅": 1.2,
                    "上涨家数": 30,
                    "下跌家数": 10,
                    "均价": 12.5,
                    "领涨股": "平安银行",
                    "领涨股-涨跌幅": 4.5,
                }
            ]
        ),
    )

    sectors = await AKShareDataSource().fetch_sectors("industry")

    assert len(sectors) == 1
    assert sectors[0].code == "881155"
    assert sectors[0].latest_price == Decimal("12.5")
    assert sectors[0].pct_change == Decimal("1.2")
    assert sectors[0].advancers == 30
    assert sectors[0].leading_stock == "平安银行"
