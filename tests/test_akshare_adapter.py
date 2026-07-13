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
            [{"code": "600000", "name": "浦发银行"}, {"code": "000001", "name": "平安银行"}]
        ),
    )
    stocks = await AKShareDataSource().fetch_stock_list()
    assert [(x.symbol, x.exchange) for x in stocks] == [("600000", "SSE"), ("000001", "SZSE")]


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
