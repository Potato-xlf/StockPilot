import asyncio
import time

from fastapi import APIRouter

from app.data_sources import AKShareDataSource
from app.schemas.status import DataSourceStatusResponse

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
