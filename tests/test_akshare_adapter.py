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
