from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class DataQualityResponse(BaseModel):
    status: Literal["ok", "warning", "error"]
    latest_trade_date: date | None
    expected_trade_date: date | None
    managed_stocks: int
    quoted_stocks: int
    coverage_pct: float
    invalid_ohlc_rows: int
    nonpositive_volume_rows: int
    missing_amount_rows: int
    amount_coverage_pct: float
    last_sync_status: str | None
    last_sync_finished_at: datetime | None
    message: str


class MarketOverviewResponse(BaseModel):
    as_of: date
    previous_trade_date: date | None
    scope: Literal["managed_universe"] = "managed_universe"
    universe_size: int
    quoted_stocks: int
    comparison_stocks: int
    advancers: int
    decliners: int
    unchanged: int
    advance_decline_ratio: float | None
    average_pct_change: float | None
    total_amount: float | None
    amount_coverage_pct: float
    data_quality_status: Literal["ok", "warning", "error"]
