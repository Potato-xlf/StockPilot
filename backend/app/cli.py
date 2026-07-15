import asyncio
import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import typer

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.data_sources import AKShareDataSource
from app.db.session import SessionLocal, engine
from app.services.market_sync import MarketSyncService
from app.services.sector_sync import SectorSyncService

app = typer.Typer(no_args_is_help=True)
DAILY_DATA_READY_TIME = time(15, 30)


def _market_now(timezone: str) -> datetime:
    return datetime.now(ZoneInfo(timezone))


def _completed_daily_as_of(timezone: str):
    now = _market_now(timezone)
    return now.date() if now.time() >= DAILY_DATA_READY_TIME else now.date() - timedelta(days=1)


@app.callback()
def main() -> None:
    """StockPilot maintenance commands."""


@app.command("sync-market-data")
def sync_market_data(
    days: int = typer.Option(30, min=1, help="Number of recent trading days"),
    limit: int | None = typer.Option(None, min=1, help="Limit symbols for smoke tests"),
) -> None:
    """Fetch the A-share list and recent daily quotes, then idempotently upsert them."""
    configure_logging()
    settings = get_settings()

    async def run() -> None:
        service = MarketSyncService(
            AKShareDataSource(),
            SessionLocal,
            settings.akshare_request_concurrency,
            settings.akshare_request_retries,
        )
        try:
            result = await service.sync(
                days=days,
                limit=limit,
                as_of=_completed_daily_as_of(settings.market_timezone),
            )
            typer.echo(json.dumps(result.__dict__, ensure_ascii=False))
            if result.failed_symbols:
                raise typer.Exit(code=2)
        finally:
            await engine.dispose()

    asyncio.run(run())


@app.command("sync-incremental")
def sync_incremental(
    lookback_days: int = typer.Option(
        5, min=1, help="Overlap window of recent trading days"
    ),
    limit: int | None = typer.Option(
        None, min=1, help="Limit the managed universe for smoke tests"
    ),
) -> None:
    """Update the managed stock universe after close; skip non-trading days."""
    configure_logging()
    settings = get_settings()

    async def run() -> None:
        service = MarketSyncService(
            AKShareDataSource(),
            SessionLocal,
            settings.akshare_request_concurrency,
            settings.akshare_request_retries,
        )
        try:
            as_of = _completed_daily_as_of(settings.market_timezone)
            result = await service.sync_incremental(
                lookback_days=lookback_days,
                limit=limit,
                as_of=as_of,
            )
            typer.echo(json.dumps(result.__dict__, ensure_ascii=False))
            if result.failed_symbols:
                raise typer.Exit(code=2)
        finally:
            await engine.dispose()

    asyncio.run(run())


@app.command("sync-stock-universe")
def sync_stock_universe(
    limit: int | None = typer.Option(None, min=1, help="Limit symbols for smoke tests"),
) -> None:
    """Refresh A-share metadata without enabling daily quote downloads."""
    configure_logging()
    settings = get_settings()

    async def run() -> None:
        service = MarketSyncService(
            AKShareDataSource(),
            SessionLocal,
            settings.akshare_request_concurrency,
            settings.akshare_request_retries,
        )
        try:
            result = await service.sync_stock_universe(limit=limit)
            typer.echo(json.dumps(result.__dict__, ensure_ascii=False))
        finally:
            await engine.dispose()

    asyncio.run(run())


@app.command("sync-quote-batch")
def sync_quote_batch(
    days: int = typer.Option(30, min=1, help="Number of recent trading days"),
    batch_size: int = typer.Option(100, min=1, max=500, help="Symbols per batch"),
    offset: int = typer.Option(0, min=0, help="Ordered stock-universe offset"),
) -> None:
    """Enable and backfill a controlled batch from the full stock universe."""
    configure_logging()
    settings = get_settings()

    async def run() -> None:
        service = MarketSyncService(
            AKShareDataSource(),
            SessionLocal,
            settings.akshare_request_concurrency,
            settings.akshare_request_retries,
        )
        try:
            result = await service.sync_quote_batch(
                days=days,
                batch_size=batch_size,
                offset=offset,
                as_of=_completed_daily_as_of(settings.market_timezone),
            )
            typer.echo(json.dumps(result.__dict__, ensure_ascii=False))
            if result.failed_symbols:
                raise typer.Exit(code=2)
        finally:
            await engine.dispose()

    asyncio.run(run())


@app.command("sync-sector-data")
def sync_sector_data(
    sector_type: str = typer.Option(
        "industry", help="Sector type: industry or concept"
    ),
    limit: int | None = typer.Option(None, min=1, help="Limit sectors for smoke tests"),
    include_members: bool = typer.Option(
        True, "--members/--no-members", help="Refresh sector constituents"
    ),
) -> None:
    """Refresh industry or concept sectors, snapshots, and constituents."""
    if sector_type not in {"industry", "concept"}:
        raise typer.BadParameter("must be industry or concept", param_hint="sector-type")
    configure_logging()
    settings = get_settings()

    async def run() -> None:
        service = SectorSyncService(
            AKShareDataSource(),
            SessionLocal,
            concurrency=min(settings.akshare_request_concurrency, 2),
            retries=settings.akshare_request_retries,
        )
        try:
            result = await service.sync(
                sector_type=sector_type,
                trade_date=_market_now(settings.market_timezone).date(),
                limit=limit,
                include_members=include_members,
            )
            typer.echo(json.dumps(result.__dict__, ensure_ascii=False))
            if result.failed_sectors:
                raise typer.Exit(code=2)
        finally:
            await engine.dispose()

    asyncio.run(run())


if __name__ == "__main__":
    app()
