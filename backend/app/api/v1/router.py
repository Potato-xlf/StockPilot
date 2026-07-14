import asyncio
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_sources import AKShareDataSource
from app.db.session import get_session
from app.schemas.market import DataQualityResponse, MarketOverviewResponse
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
