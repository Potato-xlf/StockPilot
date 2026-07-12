import asyncio
import json

import typer

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.data_sources import AKShareDataSource
from app.db.session import SessionLocal, engine
from app.services.market_sync import MarketSyncService

app = typer.Typer(no_args_is_help=True)


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
            result = await service.sync(days=days, limit=limit)
            typer.echo(json.dumps(result.__dict__, ensure_ascii=False))
            if result.failed_symbols:
                raise typer.Exit(code=2)
        finally:
            await engine.dispose()

    asyncio.run(run())


if __name__ == "__main__":
    app()
