import asyncio
import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_sources import AKShareDataSource
from app.db.session import get_session
from app.schemas.market import (
    DataQualityResponse,
    MarketOverviewResponse,
    SectorRankingResponse,
    StockListResponse,
    StockQuotesResponse,
    SyncRunsResponse,
    UniverseStatusResponse,
)
from app.schemas.status import DataSourceStatusResponse
from app.services.market_insights import MarketInsightsService

router = APIRouter(prefix="/api/v1")
DATA_SOURCE_STATUS_TIMEOUT_SECONDS = 15


@router.get("/data-source/status", response_model=DataSourceStatusResponse)
async def data_source_status() -> DataSourceStatusResponse:
    source = AKShareDataSource()
    started = time.perf_counter()
    try:
        await asyncio.wait_for(
            source.health_check(), timeout=DATA_SOURCE_STATUS_TIMEOUT_SECONDS
        )
        return DataSourceStatusResponse(
            name=source.name,
            status="ok",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            message="AKShare is reachable",
        )
    except TimeoutError:
        return DataSourceStatusResponse(
            name=source.name,
            status="error",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            message=(
                "AKShare health check timed out after "
                f"{DATA_SOURCE_STATUS_TIMEOUT_SECONDS} seconds"
            ),
        )
    except Exception as exc:
        return DataSourceStatusResponse(
            name=source.name,
            status="error",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            message=str(exc),
        )


@router.get("/data-quality/status", response_model=DataQualityResponse)
async def data_quality_status(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DataQualityResponse:
    snapshot = await MarketInsightsService(session).data_quality()
    return DataQualityResponse(**snapshot.__dict__)


@router.get("/market/overview", response_model=MarketOverviewResponse)
async def market_overview(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MarketOverviewResponse:
    snapshot = await MarketInsightsService(session).market_overview()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="market data is not available")
    return MarketOverviewResponse(**snapshot.__dict__)


@router.get("/universe/status", response_model=UniverseStatusResponse)
async def universe_status(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UniverseStatusResponse:
    snapshot = await MarketInsightsService(session).universe_status()
    return UniverseStatusResponse(**snapshot.__dict__)


@router.get("/sectors/ranking", response_model=SectorRankingResponse)
async def sector_ranking(
    session: Annotated[AsyncSession, Depends(get_session)],
    sector_type: Literal["industry", "concept"] = "industry",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SectorRankingResponse:
    snapshot = await MarketInsightsService(session).sector_ranking(sector_type, limit)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"{sector_type} sector data is not available",
        )
    return SectorRankingResponse(
        as_of=snapshot.as_of,
        previous_trade_date=snapshot.previous_trade_date,
        sector_type=snapshot.sector_type,
        total_sectors=snapshot.total_sectors,
        items=[item.__dict__ for item in snapshot.items],
    )


@router.get("/sync/runs", response_model=SyncRunsResponse)
async def sync_runs(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SyncRunsResponse:
    """Return recent market and sector sync runs for operations and dashboards."""
    data_runs, sector_runs = await MarketInsightsService(session).sync_runs(limit)
    return SyncRunsResponse(
        data_runs=[run.__dict__ for run in data_runs],
        sector_runs=[run.__dict__ for run in sector_runs],
    )


@router.get("/stocks", response_model=StockListResponse)
async def stocks(
    session: Annotated[AsyncSession, Depends(get_session)],
    q: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    exchange: Annotated[str | None, Query(min_length=3, max_length=8)] = None,
    quote_enabled: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> StockListResponse:
    items, total = await MarketInsightsService(session).stocks(
        query=q,
        exchange=exchange,
        quote_enabled=quote_enabled,
        limit=limit,
        offset=offset,
    )
    return StockListResponse(
        items=[item.__dict__ for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/stocks/{symbol}/quotes", response_model=StockQuotesResponse)
async def stock_quotes(
    symbol: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=365)] = 30,
) -> StockQuotesResponse:
    normalized = symbol.strip()
    if len(normalized) != 6 or not normalized.isdigit():
        raise HTTPException(status_code=422, detail="symbol must be a 6-digit code")
    snapshot = await MarketInsightsService(session).stock_quotes(normalized, limit)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="stock not found")
    return StockQuotesResponse(
        symbol=snapshot.symbol,
        name=snapshot.name,
        items=[item.__dict__ for item in snapshot.items],
    )
