import time

from fastapi import APIRouter

from app.data_sources import AKShareDataSource
from app.schemas.status import DataSourceStatusResponse

router = APIRouter(prefix="/api/v1")


@router.get("/data-source/status", response_model=DataSourceStatusResponse)
async def data_source_status() -> DataSourceStatusResponse:
    source = AKShareDataSource()
    started = time.perf_counter()
    try:
        await source.health_check()
        return DataSourceStatusResponse(
            name=source.name,
            status="ok",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            message="AKShare is reachable",
        )
    except Exception as exc:
        return DataSourceStatusResponse(
            name=source.name,
            status="error",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            message=str(exc),
        )
