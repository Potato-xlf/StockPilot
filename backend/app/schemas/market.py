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


class SectorRankingItemResponse(BaseModel):
    rank: int
    previous_rank: int | None
    rank_change: int | None
    code: str
    name: str
    score: float
    pct_change: float | None
    turnover_rate: float | None
    breadth_pct: float | None
    advancers: int | None
    decliners: int | None
    leading_stock: str | None
    leading_stock_pct: float | None
    member_count: int


class SectorRankingResponse(BaseModel):
    as_of: date
    previous_trade_date: date | None
    sector_type: Literal["industry", "concept"]
    total_sectors: int
    items: list[SectorRankingItemResponse]


class UniverseStatusResponse(BaseModel):
    total_listed_stocks: int
    quote_enabled_stocks: int
    pending_quote_stocks: int
    exchange_counts: dict[str, int]
    last_universe_sync_status: str | None
    last_universe_sync_finished_at: datetime | None
    last_quote_batch_status: str | None
    last_quote_batch_finished_at: datetime | None


class DataSyncRunResponse(BaseModel):
    id: int
    job_type: str
    status: str
    requested_days: int
    stock_count: int
    quote_count: int
    failed_symbols: int
    message: str | None
    started_at: datetime
    finished_at: datetime | None


class SectorSyncRunResponse(BaseModel):
    id: int
    sector_type: str
    status: str
    sector_count: int
    member_count: int
    failed_sectors: int
    message: str | None
    started_at: datetime
    finished_at: datetime | None


class SyncRunsResponse(BaseModel):
    data_runs: list[DataSyncRunResponse]
    sector_runs: list[SectorSyncRunResponse]
