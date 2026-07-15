import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tenacity import retry, stop_after_attempt, wait_exponential

from app.data_sources.base import MarketDataSource, SectorRecord
from app.models import Sector, SectorMember, SectorSnapshot, SectorSyncRun, Stock

logger = logging.getLogger(__name__)


@dataclass
class SectorSyncResult:
    run_id: int | None = None
    status: str = "running"
    sector_type: str = "industry"
    sectors: int = 0
    members: int = 0
    failed_sectors: int = 0
    message: str | None = None


class SectorSyncService:
    def __init__(
        self,
        source: MarketDataSource,
        session_factory: async_sessionmaker[AsyncSession],
        concurrency: int = 2,
        retries: int = 3,
    ):
        self.source = source
        self.session_factory = session_factory
        self.semaphore = asyncio.Semaphore(concurrency)
        self.retries = retries

    async def _start_run(self, sector_type: str) -> int:
        async with self.session_factory() as session, session.begin():
            run = SectorSyncRun(sector_type=sector_type, status="running")
            session.add(run)
            await session.flush()
            return run.id

    async def _finish_run(self, result: SectorSyncResult) -> None:
        if result.run_id is None:
            return
        async with self.session_factory() as session, session.begin():
            await session.execute(
                update(SectorSyncRun)
                .where(SectorSyncRun.id == result.run_id)
                .values(
                    status=result.status,
                    sector_count=result.sectors,
                    member_count=result.members,
                    failed_sectors=result.failed_sectors,
                    message=result.message,
                    finished_at=datetime.now(UTC),
                )
            )

    async def _upsert_sector_catalog(
        self, sectors: list[SectorRecord], trade_date: date
    ) -> None:
        async with self.session_factory() as session, session.begin():
            sector_rows = [
                {
                    "sector_type": sector.sector_type,
                    "code": sector.code,
                    "name": sector.name,
                    "source": self.source.name,
                }
                for sector in sectors
            ]
            statement = insert(Sector).values(sector_rows)
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=["sector_type", "code"],
                    set_={
                        "name": statement.excluded.name,
                        "source": statement.excluded.source,
                        "updated_at": datetime.now(UTC),
                    },
                )
            )
            snapshot_rows = [
                {
                    "sector_type": sector.sector_type,
                    "sector_code": sector.code,
                    "trade_date": trade_date,
                    "latest_price": sector.latest_price,
                    "pct_change": sector.pct_change,
                    "turnover_rate": sector.turnover_rate,
                    "total_market_cap": sector.total_market_cap,
                    "advancers": sector.advancers,
                    "decliners": sector.decliners,
                    "leading_stock": sector.leading_stock,
                    "leading_stock_pct": sector.leading_stock_pct,
                    "source": self.source.name,
                }
                for sector in sectors
            ]
            snapshot_statement = insert(SectorSnapshot).values(snapshot_rows)
            await session.execute(
                snapshot_statement.on_conflict_do_update(
                    index_elements=["sector_type", "sector_code", "trade_date"],
                    set_={
                        column: getattr(snapshot_statement.excluded, column)
                        for column in snapshot_rows[0]
                        if column not in {"sector_type", "sector_code", "trade_date"}
                    }
                    | {"captured_at": datetime.now(UTC)},
                )
            )

    async def _replace_members(self, sector: SectorRecord) -> int:
        async with self.semaphore:

            @retry(
                stop=stop_after_attempt(self.retries),
                wait=wait_exponential(min=1, max=8),
                reraise=True,
            )
            async def fetch():
                return await self.source.fetch_sector_members(
                    sector.code, sector.sector_type
                )

            members = await fetch()
        if not members:
            raise RuntimeError(f"No members returned for sector {sector.code}")
        async with self.session_factory() as session, session.begin():
            stock_statement = insert(Stock).values(
                [
                    {
                        "symbol": member.symbol,
                        "name": member.name,
                        "exchange": member.exchange,
                        "list_status": "listed",
                        "source": self.source.name,
                    }
                    for member in members
                ]
            )
            await session.execute(
                stock_statement.on_conflict_do_update(
                    index_elements=["symbol"],
                    set_={
                        "name": stock_statement.excluded.name,
                        "exchange": stock_statement.excluded.exchange,
                        "list_status": "listed",
                        "source": stock_statement.excluded.source,
                    },
                )
            )
            await session.execute(
                delete(SectorMember).where(
                    SectorMember.sector_type == sector.sector_type,
                    SectorMember.sector_code == sector.code,
                )
            )
            await session.execute(
                insert(SectorMember).values(
                    [
                        {
                            "sector_type": sector.sector_type,
                            "sector_code": sector.code,
                            "symbol": member.symbol,
                            "source": self.source.name,
                        }
                        for member in members
                    ]
                )
            )
        return len(members)

    async def sync(
        self,
        sector_type: str,
        trade_date: date,
        limit: int | None = None,
        include_members: bool = True,
    ) -> SectorSyncResult:
        if sector_type not in {"industry", "concept"}:
            raise ValueError("sector_type must be industry or concept")
        result = SectorSyncResult(
            run_id=await self._start_run(sector_type), sector_type=sector_type
        )
        try:
            @retry(
                stop=stop_after_attempt(self.retries),
                wait=wait_exponential(min=1, max=8),
                reraise=True,
            )
            async def fetch_sectors():
                return await self.source.fetch_sectors(sector_type)

            sectors = await fetch_sectors()
            unique_sectors: dict[tuple[str, str], SectorRecord] = {}
            for sector in sectors:
                unique_sectors.setdefault((sector.sector_type, sector.code), sector)
            if len(unique_sectors) != len(sectors):
                logger.warning(
                    "deduplicated sector catalog type=%s rows=%d unique=%d",
                    sector_type,
                    len(sectors),
                    len(unique_sectors),
                )
            sectors = list(unique_sectors.values())
            if limit is not None:
                sectors = sectors[:limit]
            if not sectors:
                raise RuntimeError(f"No {sector_type} sectors returned by data source")
            await self._upsert_sector_catalog(sectors, trade_date)
            result.sectors = len(sectors)

            if include_members:
                async def sync_members(sector: SectorRecord) -> None:
                    try:
                        count = await self._replace_members(sector)
                        result.members += count
                        logger.info(
                            "synced sector members type=%s code=%s rows=%d",
                            sector.sector_type,
                            sector.code,
                            count,
                        )
                    except Exception:
                        result.failed_sectors += 1
                        logger.exception(
                            "failed sector members type=%s code=%s",
                            sector.sector_type,
                            sector.code,
                        )

                await asyncio.gather(*(sync_members(sector) for sector in sectors))

            result.status = "completed" if result.failed_sectors == 0 else "partial"
            if result.failed_sectors:
                result.message = f"{result.failed_sectors} sectors failed"
            await self._finish_run(result)
            logger.info(
                "sector sync complete run_id=%s type=%s sectors=%d members=%d failed=%d",
                result.run_id,
                sector_type,
                result.sectors,
                result.members,
                result.failed_sectors,
            )
            return result
        except Exception as exc:
            result.status = "error"
            result.message = str(exc)[:512]
            await self._finish_run(result)
            logger.exception("sector sync failed run_id=%s", result.run_id)
            raise
